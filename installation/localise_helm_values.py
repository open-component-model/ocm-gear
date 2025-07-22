#!/usr/bin/env python3

import argparse
import logging
import os

import yaml

import ci.log
import oci.client
import cnudie.retrieve
import ocm
import ocm.helm


logger = logging.getLogger(__name__)
ci.log.configure_default_logging()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--component', required=True)
    parser.add_argument('--values-file', required=True)
    parser.add_argument('--ocm-repo', required=True)
    args = parser.parse_args()

    oci_client = oci.client.Client()
    lookup = cnudie.retrieve.create_default_component_descriptor_lookup(
        ocm_repository_lookup=cnudie.retrieve.ocm_repository_lookup(args.ocm_repo),
        oci_client=oci_client,
    )

    component = lookup(args.component).component

    resource = next(
        (r for r in component.resources if r.type == 'helmchart-imagemap'),
        None
    )
    if not resource:
        logger.info(f'No helmchart-imagemap found in {args.component}, skipping.')
        return

    logger.info(f'Patching values in {args.values_file} ...')

    if os.path.exists(args.values_file):
        with open(args.values_file) as f:
            base_values = yaml.safe_load(f)
    else:
        base_values = {}

    patched_values = ocm.helm.localised_helmchart_values(
        component=component,
        oci_client=oci_client,
        resource_name=resource.name,
        resource_version=resource.version,
        resource_extra_id=resource.extraIdentity,
        base_values=base_values,
    )

    with open(args.values_file, 'w') as f:
        yaml.safe_dump(patched_values, f)

    logger.info(f'Patched image references for {args.component}')


if __name__ == '__main__':
    main()
