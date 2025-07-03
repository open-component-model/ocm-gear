import argparse
import logging
import os

import ccc.oci
import ci.log
import ci.util
import cnudie.retrieve
import ctt.process_dependencies
import ocm

ci.log.configure_default_logging()
logger = logging.getLogger(__name__)

own_dir = os.path.abspath(os.path.dirname(__file__))
repo_root = os.path.abspath(os.path.join(own_dir, os.pardir))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--component-descriptor-path',
        required=True,
        help='Path to the component descriptor YAML file.',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    cd_path = args.component_descriptor_path

    component_descriptor = ocm.ComponentDescriptor.from_dict(
        component_descriptor_dict=ci.util.parse_yaml_file(cd_path),
    )
    source_repo = 'europe-docker.pkg.dev/gardener-project/releases'
    tgt_ocm_repo_path = 'releases/odg'

    oci_client = ccc.oci.oci_client()

    lookup = cnudie.retrieve.create_default_component_descriptor_lookup(
        ocm_repository_lookup=cnudie.retrieve.ocm_repository_lookup(source_repo),
        oci_client=oci_client,
    )

    tuple(
        ctt.process_dependencies.process_images(
            processing_cfg_path=os.path.join(repo_root, 'processing.cfg'),
            root_component_descriptor=component_descriptor,
            component_descriptor_lookup=lookup,
            inject_ocm_coordinates_into_oci_manifests=True,
            oci_client=oci_client,
            tgt_ocm_repo_path=tgt_ocm_repo_path,
        )
    )

    logger.info('Image replication completed.')


if __name__ == '__main__':
    main()
