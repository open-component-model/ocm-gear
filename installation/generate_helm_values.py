#!/usr/bin/env python3

import argparse
import collections.abc
import logging
import os

import yaml

import ctx
import model

import odg.findings
import odg.scan_cfg
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


def cache_manager_cfg_if_specified(
    extension_cfg,
):
    try:
        return extension_cfg.cacheManager()
    except:
        logger.warning('cache-manager cfg not found')

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
        if extension_cfg.raw.get('cacheManager'):
            enabled_extensions.add('cacheManager')
        if extension_cfg.raw.get('deliveryDbBackup'):
            enabled_extensions.add('deliveryDbBackup')
        if extension_cfg.raw.get('issueReplicator'):
            enabled_extensions.add('backlogController')
            enabled_extensions.add('issueReplicator')
        if extension_cfg.raw.get('sast'):
            enabled_extensions.add('backlogController')
            enabled_extensions.add('sast')

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
        'annotations': ingress_cfg.get('annotations', dict()),
        'class': ingress_cfg.get('class', 'nginx'),
        'hosts': ingress_cfg.get('hosts', []),
        'tlsHostNames': ingress_cfg.get('tls_host_names', []),
    }


def bootstrapping_helm_values(
    cfg_set: model.ConfigurationSet,
) -> dict:
    findings_raw = cfg_set.findings_cfg().raw.get('findings', [])
    odg.findings.Finding.from_dict(findings_raw) # validate model classes

    scan_cfg_raw = cfg_set.scan_cfg().raw
    odg.scan_cfg.ScanConfiguration.from_dict(dict(scan_cfg_raw)) # validate model classes

    secret_factory = secret_mgmt.SecretFactory.from_cfg_factory(cfg_set.cfg_set())
    secrets = secret_factory.serialise()

    return {
        'findings': findings_raw,
        'scan_cfg': scan_cfg_raw,
        'secrets': secrets,
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
        'args': [],
        'envVars': env_vars,
        'pod': pod_helm_values(
            cfg=delivery_service_cfg,
        ),
        'autoscaler': autoscaler_helm_values(delivery_service_cfg),
        'ingress': ingress_helm_values(delivery_service_cfg.ingress()),
        'featuresCfg': delivery_service_cfg.features_cfg(),
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
    extension_cfgs = extension_cfgs_if_specified(
        cfg_set=cfg_set,
    )
    delivery_service_cfg = cfg_set.delivery_service()

    scan_cfg_raw = cfg_set.scan_cfg().raw
    scan_cfg: odg.scan_cfg.ScanConfiguration = odg.scan_cfg.ScanConfiguration.from_dict(scan_cfg_raw)

    def iter_helm_values() -> collections.abc.Generator[tuple[str, dict], None, None]:
        rescoring_cfg = delivery_service_cfg.features_cfg().get('rescoring')

        def iter_scan_cfgs(
            extension_cfgs: collections.abc.Iterable[model.NamedModelElement],
            rescoring_cfg: dict | None,
        ) -> collections.abc.Generator[dict, None, None]:
            for extension_cfg in extension_cfgs:
                if rescoring_cfg:
                    # inject rescoring-cfg to avoid duplication
                    extension_cfg.raw['defaults']['rescoring'] = rescoring_cfg
                yield {
                    'name': normalize_name(extension_cfg.name()),
                    'spec': extension_cfg.raw,
                }

        configuration = {
            'scanConfigurations': [
                scan_cfg
                for scan_cfg in iter_scan_cfgs(
                    extension_cfgs=extension_cfgs,
                    rescoring_cfg=rescoring_cfg,
                )
            ],
        }
        yield 'configuration', configuration

        if artefact_enumerator := scan_cfg.artefact_enumerator:
            artefact_enumerator = {
                'enabled': True,
                'schedule': artefact_enumerator.schedule,
                'successful_jobs_history_limit': artefact_enumerator.successful_jobs_history_limit,
                'failed_jobs_history_limit': artefact_enumerator.failed_jobs_history_limit,
            }
            yield 'artefact-enumerator', artefact_enumerator

        if backlog_controller := scan_cfg.backlog_controller:
            backlog_controller = {
                'enabled': True,
                'scanConfigurations': [
                    normalize_name(extension_cfg.name())
                    for extension_cfg in extension_cfgs
                ],
            }
            yield 'backlog-controller', backlog_controller

        if cache_manager := scan_cfg.cache_manager:
            cache_manager = {
                'enabled': True,
                'schedule': cache_manager.schedule,
                'successful_jobs_history_limit': cache_manager.successful_jobs_history_limit,
                'failed_jobs_history_limit': cache_manager.failed_jobs_history_limit,
                'args': ['--invalid-semver-ok'] if delivery_service_cfg.invalid_semver_ok() else [],
            }
            yield 'cache-manager', cache_manager

        if delivery_db_backup := scan_cfg.delivery_db_backup:
            delivery_db_backup = {
                'enabled': True,
                'schedule': delivery_db_backup.schedule,
                'successful_jobs_history_limit': delivery_db_backup.successful_jobs_history_limit,
                'failed_jobs_history_limit': delivery_db_backup.failed_jobs_history_limit,
            }
            yield 'delivery-db-backup', delivery_db_backup

        if scan_cfg.clamav:
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
        '--out-dir',
        default=os.path.join(own_dir, 'helm-values'),
    )

    return parser.parse_args()


def main():
    parsed_arguments = parse_args()

    cfg_dir = parsed_arguments.cfg_dir
    cfg_set_name = parsed_arguments.cfg_set
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
        helm_values=bootstrapping_helm_values(
            cfg_set=cfg_set,
        ),
        out_file=os.path.join(out_dir, 'values-bootstrapping.yaml'),
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
