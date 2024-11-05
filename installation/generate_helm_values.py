#!/usr/bin/env python3

import argparse
import base64
import collections.abc
import logging
import os

import yaml

import ctx
import model

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


def delivery_db_backup_cfg_if_specified(
    extension_cfg,
):
    try:
        return extension_cfg.deliveryDbBackup()
    except:
        logger.warning('delivery-db-backup cfg not found')

    return None


def prometheus_cfg_if_specified(
    cfg_set: model.ConfigurationSet,
):
    try:
        return cfg_set.prometheus()
    except:
        logger.warning('prometheus cfg not found')

    return None


def extension_cfgs_if_specified(
    cfg_set: model.ConfigurationSet,
) -> tuple:
    try:
        return tuple(cfg_set._cfg_elements(cfg_type_name='delivery_gear_extensions'))
    except:
        logger.warning('extensions cfgs not found')

    return tuple()


def enabled_extensions(
    extension_cfgs: tuple,
) -> set[str]:
    enabled_extensions = set()

    for extension_cfg in extension_cfgs:
        if extension_cfg.raw.get('artefactEnumerator'):
            enabled_extensions.add('artefactEnumerator')
        if extension_cfg.raw.get('bdba'):
            enabled_extensions.add('backlogController')
            enabled_extensions.add('bdba')
        if extension_cfg.raw.get('clamav'):
            enabled_extensions.add('backlogController')
            enabled_extensions.add('clamav')
        if extension_cfg.raw.get('deliveryDbBackup'):
            enabled_extensions.add('deliveryDbBackup')
        if extension_cfg.raw.get('issueReplicator'):
            enabled_extensions.add('backlogController')
            enabled_extensions.add('issueReplicator')

    return enabled_extensions


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


def ingress_helm_values(
    ingress_cfg: dict,
) -> dict:
    return {
        'annotations': ingress_cfg.get('annotations', dict()),
        'class': ingress_cfg.get('class', 'nginx'),
        'hosts': ingress_cfg.get('hosts', []),
        'tlsHostNames': ingress_cfg.get('tls_host_names', []),
    }


def serialise_cfg_factory(
    cfg_factory: model.ConfigFactory,
    cfg_set: model.ConfigurationSet,
) -> str:
    # serialise cfg factory as json
    cfg_sets = [cfg_set.cfg_set()]
    serialiser = model.ConfigSetSerialiser(
        cfg_sets=cfg_sets,
        cfg_factory=cfg_factory,
    )
    serialised = serialiser.serialise().encode('utf-8')
    return base64.b64encode(serialised).decode('utf-8')


def common_env_vars(
    cfg_set: model.ConfigurationSet,
    namespace: str,
) -> dict[str, str]:
    env_vars = {
        'CFG_FACTORY_SECRET_PATH': '/cfg_factory/cfg_factory',
        'FEATURES_CFG_PATH': '/features_cfg/features_cfg',
        'K8S_TARGET_NAMESPACE': namespace,
    }

    try:
        kubernetes_cfg_name = cfg_set.cfg_set().kubernetes().name()
        env_vars['K8S_CFG_NAME'] = kubernetes_cfg_name
    except:
        pass

    return env_vars


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
    namespace: str,
    create_cfg_factory: bool=False,
    cfg_factory: model.ConfigFactory=None,
) -> dict:
    delivery_service_cfg = cfg_set.delivery_service()

    env_vars = common_env_vars(
        cfg_set=cfg_set,
        namespace=namespace,
    )

    try:
        extra_env_vars = [
            [
                env_var.get('name'),
                f'"{env_var.get("value")}"',
            ]
            for env_var in delivery_service_cfg.env()
        ]
        env_vars = env_vars | dict(extra_env_vars)
    except AttributeError:
        pass

    helm_values = {
        'args': [
            '--delivery-cfg',
            cfg_set.delivery().name(),
            '--delivery-endpoints',
            cfg_set.delivery_endpoints().name(),
        ],
        'envVars': env_vars,
        'pod': pod_helm_values(
            cfg=delivery_service_cfg,
        ),
        'ingress': ingress_helm_values(delivery_service_cfg.ingress()),
        'replicas': delivery_service_cfg.replicas(),
        'featuresCfg': delivery_service_cfg.features_cfg(),
        'createCfgFactorySecret': create_cfg_factory,
    }

    if delivery_db_cfg := delivery_db_cfg_if_specified(
        cfg_set=cfg_set,
    ):
        helm_values['args'].append('--delivery-db-cfg')
        helm_values['args'].append(delivery_db_cfg.name())

    if delivery_service_cfg.invalid_semver_ok():
        helm_values['args'].append('--invalid-semver-ok')

    extension_cfgs = extension_cfgs_if_specified(
        cfg_set=cfg_set,
    )
    if extensions := enabled_extensions(
        extension_cfgs=extension_cfgs,
    ):
        helm_values['args'].append('--service-extensions')
        helm_values['args'].extend(extensions)

    if create_cfg_factory:
        helm_values['cfgFactory'] = serialise_cfg_factory(
            cfg_factory=cfg_factory,
            cfg_set=cfg_set,
        )

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
    namespace: str,
):
    env_vars = common_env_vars(
        cfg_set=cfg_set,
        namespace=namespace,
    )

    extension_cfgs = extension_cfgs_if_specified(
        cfg_set=cfg_set,
    )

    def iter_delivery_db_backup_cfg(extension_cfg):
        db_backup_cfg = delivery_db_backup_cfg_if_specified(extension_cfg)

        if not db_backup_cfg:
            return

        yield 'DELIVERY_GEAR_CFG_NAME', normalize_name(extension_cfg.name())
        yield 'SCHEDULE', db_backup_cfg['schedule']
        yield 'SUCCESSFUL_JOBS_HISTORY_LIMIT', db_backup_cfg['successful_jobs_history_limit']
        yield 'FAILED_JOBS_HISTORY_LIMIT', db_backup_cfg['failed_jobs_history_limit']

    delivery_db_backup_cfgs = [
        dict(
            iter_delivery_db_backup_cfg(
                extension_cfg=extension_cfg,
            ),
            **env_vars,
        )
        for extension_cfg in extension_cfgs
    ]

    def iter_helm_values() -> collections.abc.Generator[tuple[str, dict], None, None]:
        extensions = enabled_extensions(
            extension_cfgs=extension_cfgs,
        )

        artefact_enumerator_enabled = 'artefactEnumerator' in extensions
        backlog_controller_enabled = 'backlogController' in extensions
        delivery_db_backup_enabled = 'deliveryDbBackup' in extensions
        freshclam_enabled = 'clamav' in extensions

        delivery_service_cfg = cfg_set.delivery_service()

        # inject rescoring cfg from delivery-service cfg to avoid duplication
        rescoring_cfg = delivery_service_cfg.features_cfg().get('rescoring', {})
        if rescoring_cfg:
            rescoring_cfg = {'rescoring': rescoring_cfg}

        configuration = {
            'scanConfigurations': [
                {
                    'name': normalize_name(extension_cfg.name()),
                    'spec': dict(
                        **extension_cfg.raw,
                        **rescoring_cfg,
                    ),
                } for extension_cfg in extension_cfgs
            ],
        }
        yield 'configuration', configuration

        if artefact_enumerator_enabled:
            artefact_enumerator = {
                'enabled': True,
                'envVars': env_vars,
                'configuration': {},
            }
            yield 'artefact-enumerator', artefact_enumerator

        if backlog_controller_enabled:
            backlog_controller = {
                'enabled': True,
                'envVars': env_vars,
                'scanConfigurations': [
                    normalize_name(extension_cfg.name())
                    for extension_cfg in extension_cfgs
                ],
                'namespace': namespace,
            }
            yield 'backlog-controller', backlog_controller

        if delivery_db_backup_enabled:
            delivery_db_backup = {
                'enabled': True,
                'configurations': delivery_db_backup_cfgs,
            }
            yield 'delivery-db-backup', delivery_db_backup

        if freshclam_enabled:
            freshclam = {
                'enabled': True,
            }
            yield 'freshclam', freshclam

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
        '--create-cfg-factory',
        action='store_true',
        default=False,
    )
    parser.add_argument(
        '--namespace',
        default='delivery',
    )
    parser.add_argument(
        '--out-dir',
        default=os.path.join(own_dir, 'helm-values'),
    )

    return parser.parse_args()


def main():
    parsed_arguments = parse_args()

    cfg_dir = parsed_arguments.cfg_dir
    cfg_set_name = parsed_arguments.cfg_set
    create_cfg_factory = parsed_arguments.create_cfg_factory
    namespace = parsed_arguments.namespace
    out_dir = parsed_arguments.out_dir

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
        helm_values=delivery_db_helm_values(
            cfg_set=cfg_set,
        ),
        out_file=os.path.join(out_dir, 'values-delivery-db.yaml'),
    )
    write_values_to_file(
        helm_values=delivery_service_helm_values(
            cfg_set=cfg_set,
            namespace=namespace,
            create_cfg_factory=create_cfg_factory,
            cfg_factory=cfg_factory,
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
            namespace=namespace,
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
