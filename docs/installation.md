# Creating new Installation

1. [Synopsis](#synopsis)
2. [Options](#options)
3. [Example](#example)

<a id="synopsis"></a>
### Synopsis
```
$ ./deploy_ocm_gear.sh [<options>]
```

<a id="options"></a>
### Options
| Option | Description | Default | Required |
| :----- | :---------- | :------ | :------: |
| --cfg-dir | path to directory containing configuration files | `./cfg` | x |
| --cfg-set | cfg set from `configs.yaml` to use for installation | `ocm_gear` | x |
| --ingress-namespace | namespace to deploy the ingress controller into (only used if `--install-ingress-controller` is set | `ingress-nginx` | |
| --install-ingress-controller | deploy nginx controller to `--ingress-namespace` during installation | | |
| --kubeconfig | path to kubeconfig of target cluster | | x |
| --kubernetes-cfg-name | name of config element containing kubeconfig of target cluster (if set, `--kubeconfig` can be omitted) | | |
| --namespace | namespace to deploy the OCM-Gear into | `delivery` | x |
| --values-dir | path to directory containing required helm values files (`values-delivery-service.yaml`, `values-delivery-dashboard.yaml`, `values-delivery-db.yaml`, `values-extensions.yaml`, `values-prometheus-operator.yaml`), if directory does not exist, corresponding values files will be generated based on `--cfg-dir` | `./helm-values` | x |
| --version | version of `ocm.software/ocm-gear` component which should be deployed | greatest available version of `europe-docker.pkg.dev/gardener-project/releases/component-descriptors/ocm.software/ocm-gear` | |

<a id="example"></a>
### Example
```
$ ./deploy_ocm_gear.sh \
    --kubeconfig ./kubeconfig.yaml \
    --install-ingress-controller
```
