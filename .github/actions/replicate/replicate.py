#!/usr/bin/env python3

import argparse
import logging
import os

import ci.log
import ci.util
import cnudie.retrieve
import ctt.process_dependencies
import oci.auth
import oci.client
import ocm
import version as version_mod


ci.log.configure_default_logging()
logger = logging.getLogger(__name__)

own_dir = os.path.abspath(os.path.dirname(__file__))
repo_root = os.path.abspath(os.path.join(own_dir, os.pardir, os.pardir, os.pardir))


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--component-descriptor-path',
        required=False,
        help='Path to the component descriptor YAML file.',
    )
    parser.add_argument(
        '--processing-mode',
        required=False,
        default=ctt.process_dependencies.ProcessingMode.REGULAR,
        type=ctt.process_dependencies.ProcessingMode,
        help='Influences whether OCI resources are actually being replicated.',
    )
    return parser.parse_args()


def ocm_gear_version() -> str:
    version_file = os.path.join(repo_root, 'VERSION')
    with open(version_file, 'r') as file:
        version = file.read().strip()

    parsed_version = version_mod.parse_to_semver(version)

    if version_mod.is_final(parsed_version):
        return str(parsed_version)

    parsed_version = parsed_version.replace(prerelease=None)

    if parsed_version.patch:
        parsed_version = parsed_version.replace(patch=parsed_version.patch - 1)
    elif parsed_version.minor:
        parsed_version = parsed_version.replace(minor=parsed_version.minor - 1)
    elif parsed_version.major:
        parsed_version = parsed_version.replace(major=parsed_version.major - 1)

    return str(parsed_version)


def main():
    args = parse_args()

    source_repo = 'europe-docker.pkg.dev/gardener-project/releases'
    tgt_ocm_repo_path = 'releases/odg'

    oci_client = oci.client.Client(
        credentials_lookup=oci.auth.docker_credentials_lookup(),
    )

    lookup = cnudie.retrieve.create_default_component_descriptor_lookup(
        ocm_repository_lookup=cnudie.retrieve.ocm_repository_lookup(source_repo),
        oci_client=oci_client,
    )

    if component_descriptor_path := args.component_descriptor_path:
        component_descriptor = ocm.ComponentDescriptor.from_dict(
            component_descriptor_dict=ci.util.parse_yaml_file(component_descriptor_path),
        )
    else:
        component_descriptor = lookup(ocm.ComponentIdentity(
            name='ocm.software/ocm-gear',
            version=ocm_gear_version(),
        ))

    tuple(
        ctt.process_dependencies.process_images(
            processing_cfg_path=os.path.join(repo_root, 'processing.cfg'),
            root_component_descriptor=component_descriptor,
            component_descriptor_lookup=lookup,
            processing_mode=args.processing_mode,
            inject_ocm_coordinates_into_oci_manifests=True,
            oci_client=oci_client,
            tgt_ocm_repo_path=tgt_ocm_repo_path,
        )
    )

    logger.info('Image replication completed.')


if __name__ == '__main__':
    main()
