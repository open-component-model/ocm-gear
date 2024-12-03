#!/usr/bin/env python3

import argparse
import asyncio
import logging

import sqlalchemy as sa
import sqlalchemy.ext.asyncio as sqlasync
import sqlalchemy.orm.decl_api

import dso.model


Base: sqlalchemy.orm.decl_api.DeclarativeMeta = sqlalchemy.orm.declarative_base()

logger = logging.getLogger(__name__)


class ArtefactMetadata(Base):
    __tablename__ = 'artefact_metadata'

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    new_id = sa.Column(sa.CHAR(length=32))
    creation_date = sa.Column(sa.DateTime(timezone=True), server_default=sa.sql.func.now())
    type = sa.Column(sa.String(length=64))
    component_name = sa.Column(sa.String(length=256))
    component_version = sa.Column(sa.String(length=64))
    artefact_kind = sa.Column(sa.String(length=32))
    artefact_name = sa.Column(sa.String(length=128))
    artefact_version = sa.Column(sa.String(length=64))
    artefact_type = sa.Column(sa.String(length=64))
    artefact_extra_id_normalised = sa.Column(sa.String(length=1024))
    artefact_extra_id = sa.Column(sa.JSON)
    meta = sa.Column(sa.JSON, default=dict)
    data = sa.Column(sa.JSON, default=dict)
    data_key = sa.Column(sa.CHAR(length=40))
    datasource = sa.Column(sa.String(length=64))
    cfg_name = sa.Column(sa.String(length=64))
    referenced_type = sa.Column(sa.String(length=64))
    discovery_date = sa.Column(sa.Date)


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument('--db-url')

    return parser.parse_args()


async def init_db_session(parsed_arguments) -> sqlasync.session.AsyncSession:
    engine = sqlasync.create_async_engine(
        parsed_arguments.db_url,
        echo=False,
        future=True,
        pool_pre_ping=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = sqlasync.async_sessionmaker(bind=engine)
    return sessionmaker()


def db_artefact_metadata_to_dict(
    am: ArtefactMetadata,
) -> dict:
    return {
        'artefact': {
            'component_name': am.component_name,
            'component_version': am.component_version,
            'artefact_kind': am.artefact_kind,
            'artefact': {
                'artefact_name': am.artefact_name,
                'artefact_version': am.artefact_version,
                'artefact_type': am.artefact_type,
                'artefact_extra_id': am.artefact_extra_id,
            },
        },
        'meta': am.meta,
        'data': am.data,
        'discovery_date': am.discovery_date.isoformat() if am.discovery_date else None,
    }


async def main():
    parsed_arguments = parse_args()

    db_session = await init_db_session(parsed_arguments)
    db_stream = await db_session.execute(sa.select(ArtefactMetadata))

    logger.info('Going to calculate content-based primary key ids, this may take a moment...')
    for idx, partition in enumerate(db_stream.partitions(size=50)):
        if idx % 50 == 0:
            logger.info(f'Still progressing... ({idx}. iteration)')

        for row in partition:
            artefact_metadatum_raw = row[0]
            artefact_metadatum = dso.model.ArtefactMetadata.from_dict(db_artefact_metadata_to_dict(
                am=artefact_metadatum_raw,
            ))
            artefact_metadatum_raw.new_id = artefact_metadatum.id

    logger.info('Finished calculation of id, going to commit changes...')

    await db_session.commit()
    await db_session.close()


if __name__ == '__main__':
    asyncio.run(main())
