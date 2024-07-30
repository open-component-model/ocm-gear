# Prerequisites

1. [Python Environment](#python)
2. [Kubernetes Cluster](#k8s)
3. [TLS Secrets](#tls)

<a id="python"></a>

## Python3

A local Python3 environment with necessary libraries installed, e.g. via [pip](https://pypi.org/project/pip/):

```
python3 -m pip install -r requirements.txt
```

<a id="k8s"></a>

## Kubernetes Cluster

A Kubernetes cluster where the OCM-Gear should be deployed into.

<a id="tls"></a>

## TLS Secrets

If you do **not** want to use a TLS provider (such as [gardener/cert-manager](https://github.com/gardener/cert-management)), the corresponding TLS secrets are expected to be named `delivery-dashboard-tls` and `delivery-service-tls` and be located in the same namespace as the OCM-Gear is installed to.
