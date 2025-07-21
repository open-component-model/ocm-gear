#!/usr/bin/env python3

import argparse
import collections.abc
import dataclasses
import json
import logging
import os

import yaml

import ctx
import model

import odg.extensions_cfg
import odg.findings
import secret_mgmt


logger = logging.getLogger(__name__)

own_dir = os.path.abspath(os.path.dirname(__file__))
repo_dir = os.path.abspath(os.path.join(own_dir, os.pardir))


def normalize_name(
    name: str,
) -> str:
    return name.replace('_', '-')


def delivery_db_cfg_if_specified(
    cfg_set: model.ConfigurationSet,
):
    try:
        return cfg_set.delivery_db()
    except:
        logger.warning('delivery-db cfg not found')

    return None


def prometheus_cfg_if_specified(
    cfg_set: model.ConfigurationSet,
):
    try:
        return cfg_set.prometheus()
    except:
        logger.warning('prometheus cfg not found')

    return None


def pod_helm_values(
    cfg,
) -> dict:
    annotations = dict()
    labels = dict()

    try:
        annotations = cfg.pod()['annotations']
        labels = cfg.pod()['labels']
    except AttributeError:
        pass

    return {
        'annotations': annotations,
        'labels': labels,
    }


def autoscaler_helm_values(
    cfg,
) -> dict:
    try:
        return cfg.autoscaler()
    except:
        return dict()


def ingress_helm_values(
    ingress_cfg: dict,
) -> dict:
    return {
        'hosts': ingress_cfg['hosts'],
        'annotations': ingress_cfg.get('annotations'),
        'class': ingress_cfg.get('class'),
    }


def bootstrapping_helm_values(
    cfg_set: model.ConfigurationSet,
    extensions: list[odg.extensions_cfg.ExtensionDefinitionOcmReference],
) -> dict:
    findings_raw = cfg_set.findings_cfg().raw.get('findings', [])
    odg.findings.Finding.from_dict(findings_raw) # validate model classes

    extensions_cfg_raw = cfg_set.extensions_cfg().raw
    odg.extensions_cfg.ExtensionsConfiguration.from_dict(dict(extensions_cfg_raw)) # validate model classes

    extensions_cfg = odg.extensions_cfg.ExtensionsConfiguration.from_dict(extensions_cfg_raw)
    if extensions_cfg.odg_operator:
        extensions_cfg_raw['odg_operator']['extension_ocm_references'] = [
            dataclasses.asdict(extension) for extension in extensions
        ]

    # dirty: Parse referenced cfg set to a dictionary representation to create a cfg factory from it
    cfg_factory = model.ConfigFactory.from_dict(json.loads(model.ConfigSetSerialiser(
        cfg_sets=[cfg_set.cfg_set()],
        cfg_factory=cfg_set.cfg_factory,
    ).serialise()))
    secret_factory = secret_mgmt.SecretFactory.from_cfg_factory(cfg_factory)
    secrets = secret_factory.serialise()

    delivery_service_cfg = cfg_set.delivery_service()
    features_cfg: dict = delivery_service_cfg.features_cfg()
    ocm_repo_mappings = features_cfg.get('ocmRepoMappings')
    profiles = features_cfg.get('profiles')

    if 'ocmRepoMappings' in features_cfg:
        # added separately
        del features_cfg['ocmRepoMappings']
    if 'profiles' in features_cfg:
        # added separately
        del features_cfg['profiles']

    return {
        'findings': findings_raw,
        'features_cfg': features_cfg,
        'extensions_cfg': extensions_cfg_raw,
        'secrets': secrets,
        'ocm_repo_mappings': ocm_repo_mappings,
        'profiles': profiles,
    }


def delivery_db_helm_values(
    cfg_set: model.ConfigurationSet,
):
    if not (delivery_db_cfg := delivery_db_cfg_if_specified(
        cfg_set=cfg_set,
    )):
        return dict()

    helm_values = delivery_db_cfg.helm_values()
    helm_values['postgresqlPassword'] = delivery_db_cfg.credentials().password()

    return helm_values


def delivery_service_helm_values(
    cfg_set: model.ConfigurationSet,
) -> dict:
    delivery_service_cfg = cfg_set.delivery_service()

    try:
        env_vars = dict([
            [
                env_var.get('name'),
                f'"{env_var.get("value")}"',
            ]
            for env_var in delivery_service_cfg.env()
        ])
    except AttributeError:
        env_vars = {}

    helm_values = {
        'envVars': env_vars,
        'pod': pod_helm_values(delivery_service_cfg),
        'autoscaler': autoscaler_helm_values(delivery_service_cfg),
        'ingress': ingress_helm_values(delivery_service_cfg.ingress()),
    }

    if delivery_service_cfg.invalid_semver_ok():
        helm_values['args'] = ['--invalid-semver-ok']

    return helm_values


def delivery_dashboard_helm_values(
    cfg_set: model.ConfigurationSet,
) -> dict:
    delivery_service_cfg = cfg_set.delivery_service()
    delivery_dashboard_cfg = cfg_set.delivery_dashboard()

    delivery_service_url = (
        f'{delivery_service_cfg.protocol()}://'
        f'{delivery_service_cfg.ingress()["hosts"][0]}'
    )

    return {
        'envVars': {
            'REACT_APP_DELIVERY_SERVICE_API_URL': delivery_service_url,
        },
        'pod': pod_helm_values(
            cfg=delivery_dashboard_cfg,
        ),
        'ingress': ingress_helm_values(delivery_dashboard_cfg.ingress()),
        'replicas': delivery_dashboard_cfg.replicas(),
    }


def extensions_helm_values(
    cfg_set: model.ConfigurationSet,
):
    delivery_service_cfg = cfg_set.delivery_service()

    extensions_cfg_raw = cfg_set.extensions_cfg().raw
    extensions_cfg = odg.extensions_cfg.ExtensionsConfiguration.from_dict(extensions_cfg_raw)

    def iter_helm_values() -> collections.abc.Generator[tuple[str, dict], None, None]:
        def helm_values_for_extension_cfg(
            extension_cfg: odg.extensions_cfg.AccessManagerConfig
                | odg.extensions_cfg.ArtefactEnumeratorConfig
                | odg.extensions_cfg.CacheManagerConfig
                | odg.extensions_cfg.DeliveryDBBackup,
            absent_ok: bool=True,
        ) -> dict | None:
            if isinstance(extension_cfg, (
                odg.extensions_cfg.AccessManagerConfig,
                odg.extensions_cfg.ArtefactEnumeratorConfig,
                odg.extensions_cfg.DeliveryDBBackup,
            )):
                return {
                    'enabled': extension_cfg.enabled,
                    'schedule': extension_cfg.schedule,
                    'successful_jobs_history_limit': extension_cfg.successful_jobs_history_limit,
                    'failed_jobs_history_limit': extension_cfg.failed_jobs_history_limit,
                }

            elif isinstance(extension_cfg, odg.extensions_cfg.CacheManagerConfig):
                return {
                    'enabled': extension_cfg.enabled,
                    'schedule': extension_cfg.schedule,
                    'successful_jobs_history_limit': extension_cfg.successful_jobs_history_limit,
                    'failed_jobs_history_limit': extension_cfg.failed_jobs_history_limit,
                    'args': ['--invalid-semver-ok'] if delivery_service_cfg.invalid_semver_ok() else [],
                }

            else:
                if absent_ok:
                    return None

                raise ValueError(f'unsupported extension type: {type(extension_cfg)}')

        for extension_name in extensions_cfg.enabled_extensions():
            extension_cfg: odg.extensions_cfg.ExtensionCfgMixins = getattr(extensions_cfg, extension_name)
            extension_name = extension_name.replace('_', '-')

            if (helm_values := helm_values_for_extension_cfg(extension_cfg)):
                yield extension_name, helm_values

            else:
                yield extension_name, {
                    'enabled': extension_cfg.enabled,
                }

    return dict(iter_helm_values())


def prometheus_operator_helm_values(
    cfg_set: model.ConfigurationSet,
) -> dict | None:
    if not (prometheus_cfg := prometheus_cfg_if_specified(cfg_set)):
        return None

    return {
        **prometheus_cfg.raw,
        'ingress': ingress_helm_values(prometheus_cfg.ingress()),
    }


def write_values_to_file(
    helm_values: dict,
    out_file: str,
):
    with open(out_file, 'w') as file:
        file.write(yaml.safe_dump(helm_values))


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--cfg-dir',
        required=False,
    )
    parser.add_argument(
        '--cfg-set',
        required=True,
    )
    parser.add_argument(
        '--out-dir',
        default=os.path.join(own_dir, 'helm-values'),
    )
    parser.add_argument(
        '--odg-extension',
        dest='extensions',
        action='append',
        default=[],
        help='ocm references to retrieve odg extension definitions from. \
            can be specified multiple times, \
            expected format: <component-name>:<component-version>:<artefact-name>'
    )
    parser.add_argument(
        '--modg',
        default=False,
        required=False,
        help='Only generate values required for modg deployment',
        action='store_true'
    )

    return parser.parse_args()


def main():
    parsed_arguments = parse_args()

    cfg_dir = parsed_arguments.cfg_dir
    cfg_set_name = parsed_arguments.cfg_set
    out_dir = parsed_arguments.out_dir
    modg = parsed_arguments.modg
    extensions = parsed_arguments.extensions

    if cfg_dir:
        cfg_factory = model.ConfigFactory.from_cfg_dir(cfg_dir)
    else:
        cfg_factory = ctx.cfg_factory()

    cfg_set = cfg_factory.cfg_set(cfg_set_name)

    os.makedirs(
        name=out_dir,
        exist_ok=True,
    )

    write_values_to_file(
        helm_values=bootstrapping_helm_values(
            cfg_set=cfg_set,
            extensions=[
                odg.extensions_cfg.ExtensionDefinitionOcmReference(
                    component_name=extension[0],
                    component_version=extension[1],
                    artefact_name=extension[2],
                )
                for extension in [e.split(':') for e in extensions]
            ]
        ),
        out_file=os.path.join(out_dir, 'values-bootstrapping.yaml'),
    )

    if modg:
        return

    write_values_to_file(
        helm_values=delivery_db_helm_values(
            cfg_set=cfg_set,
        ),
        out_file=os.path.join(out_dir, 'values-delivery-db.yaml'),
    )
    write_values_to_file(
        helm_values=delivery_service_helm_values(
            cfg_set=cfg_set,
        ),
        out_file=os.path.join(out_dir, 'values-delivery-service.yaml'),
    )
    write_values_to_file(
        helm_values=delivery_dashboard_helm_values(
            cfg_set=cfg_set,
        ),
        out_file=os.path.join(out_dir, 'values-delivery-dashboard.yaml'),
    )
    write_values_to_file(
        helm_values=extensions_helm_values(
            cfg_set=cfg_set,
        ),
        out_file=os.path.join(out_dir, 'values-extensions.yaml'),
    )
    if prometheus_operator_values := prometheus_operator_helm_values(cfg_set):
        write_values_to_file(
            helm_values=prometheus_operator_values,
            out_file=os.path.join(out_dir, 'values-prometheus-operator.yaml'),
        )


if __name__ == '__main__':
    main()
