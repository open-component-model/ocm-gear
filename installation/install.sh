#!/usr/bin/env bash

set -euo pipefail

OWN_DIR=$(readlink -f "$(dirname "${0}")")

CFG_DIR=""
CFG_SET=""
CREATE_CFG_FACTORY=""
INGRESS_NAMESPACE=ingress-nginx
INSTALL_INGRESS_CONTROLLER=""
KUBECONFIG=""
KUBERNETES_CFG_NAME=""
NAMESPACE=delivery
OCM_GEAR_VERSION=""
VALUES_DIR="${OWN_DIR}/helm-values"

parse_flags() {
  while test $# -gt 0; do
    case "$1" in
    --cfg-dir)
      shift; CFG_DIR="$1"
      ;;
    --cfg-set)
      shift; CFG_SET="$1"
      ;;
    --create-cfg-factory)
      CREATE_CFG_FACTORY=true
      ;;
    --ingress-namespace)
      shift; INGRESS_NAMESPACE="$1"
      ;;
    --install-ingress-controller)
      INSTALL_INGRESS_CONTROLLER=true
      ;;
    --kubeconfig)
      shift; KUBECONFIG="$1"
      ;;
    --kubernetes-cfg-name)
      shift; KUBERNETES_CFG_NAME="$1"
      ;;
    --namespace)
      shift; NAMESPACE="$1"
      ;;
    --values-dir)
      shift; VALUES_DIR="$1"
      ;;
    --version)
      shift; OCM_GEAR_VERSION="$1"
      ;;
    esac

    shift
  done
}

parse_kubeconfig() {
  if [ -n "${KUBERNETES_CFG_NAME}" ]; then
    cli.py config export_kubeconfig --kubernetes-config-name ${KUBERNETES_CFG_NAME} --output-file "${OWN_DIR}/kubeconfig.yaml"
    export KUBECONFIG="${OWN_DIR}/kubeconfig.yaml"
  fi
}

check_required_flags() {
  flags=("$@")
  flag_unset=""

  for flag in "${flags[@]}"; do
    [ -z "${!flag}" ] && echo "--$(echo ${flag} | tr '[:upper:]' '[:lower:]' | tr '_' '-') must be set" && flag_unset=true
  done

  [ -n "${flag_unset}" ] && exit 1

  return 0
}

parse_flags "$@"
parse_kubeconfig
check_required_flags INGRESS_NAMESPACE KUBECONFIG NAMESPACE VALUES_DIR

if ! which ocm 1>/dev/null; then
  echo ">>> Installing OCM cli..."
  curl -s https://ocm.software/install.sh | bash
  echo ">>> Installed OCM cli in version $(ocm version)"
fi
if ! which yq 1>/dev/null; then
  echo ">>> Installing yq..."
  VERSION=v4.44.2 && BINARY=yq_linux_amd64 && wget https://github.com/mikefarah/yq/releases/download/${VERSION}/${BINARY}.tar.gz -O - | tar xz && mv ${BINARY} /usr/bin/yq
  echo ">>> Installed yq in version $(yq --version)"
fi
if ! which helm 1>/dev/null; then
  echo ">>> Installing Helm package manager..."
  DESIRED_VERSION=v3.7.0 && curl https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 | bash
  echo ">>> Installed Helm packaged manager in version $(helm version)"
fi
if ! which kubectl 1>/dev/null; then
  echo ">>> Installing kubectl..."
  curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" && chmod +x kubectl && mv kubectl /usr/bin/kubectl
  echo ">>> Installed kubectl in version $(kubectl version)"
fi

OCM_GEAR_COMPONENT_REF="europe-docker.pkg.dev/gardener-project/releases//ocm.software/ocm-gear"
OCM_GEAR_VERSION="${OCM_GEAR_VERSION:-$(ocm show versions ${OCM_GEAR_COMPONENT_REF} | tail -1)}"
COMPONENT_DESCRIPTORS=$(ocm get cv ${OCM_GEAR_COMPONENT_REF}:${OCM_GEAR_VERSION} -o yaml -r)

echo ">>> Installing OCM-Gear in version ${OCM_GEAR_VERSION}"

DELIVERY_SERVICE_CHART=$(echo "${COMPONENT_DESCRIPTORS}" | yq eval '.component.resources.[] | select(.name == "delivery-service" and .type == "helmChart/v1") | .access.imageReference')
DELIVERY_DASHBOARD_CHART=$(echo "${COMPONENT_DESCRIPTORS}" | yq eval '.component.resources.[] | select(.name == "delivery-dashboard" and .type == "helmChart/v1") | .access.imageReference')
EXTENSIONS_CHART=$(echo "${COMPONENT_DESCRIPTORS}" | yq eval '.component.resources.[] | select(.name == "extensions" and .type == "helmChart/v1") | .access.imageReference')
DELIVERY_DB_CHART=$(echo "${COMPONENT_DESCRIPTORS}" | yq eval '.component.resources.[] | select(.name == "postgresql" and .type == "helmChart/v1") | .access.imageReference')

if [ ! -d "${VALUES_DIR}" ]; then
  echo ">>> Generating required helm values into ${VALUES_DIR}"
  python3 ${OWN_DIR}/generate_helm_values.py \
    ${CFG_DIR:+"--cfg-dir"} ${CFG_DIR:+${CFG_DIR}} \
    ${CFG_SET:+"--cfg-set"} ${CFG_SET:+${CFG_SET}} \
    ${CREATE_CFG_FACTORY:+"--create-cfg-factory"} \
    --namespace ${NAMESPACE} \
    --out-dir ${VALUES_DIR}
else
  echo ">>> Found existing helm values directory ${VALUES_DIR}, will not generate helm values"
fi

if [ -n "${INSTALL_INGRESS_CONTROLLER}" ]; then
  echo ">>> Creating namespace ${INGRESS_NAMESPACE}"
  kubectl create ns ${INGRESS_NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
  kubectl config set-context --current --namespace=${INGRESS_NAMESPACE}

  echo ">>> Installing ingress nginx controller"
  helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
  helm repo update
  helm upgrade -i ingress-nginx ingress-nginx/ingress-nginx \
    --namespace ${INGRESS_NAMESPACE} \
    --set externalTrafficPolicy=Cluster
  echo ">>> Waiting for ingress nginx controller to become ready, this can take up to 90 seconds..."
  kubectl wait \
    --namespace ${INGRESS_NAMESPACE} \
    --for=condition=ready pod \
    --selector=app.kubernetes.io/component=controller \
    --timeout=90s
fi

echo ">>> Installing OCM-Gear components"

echo ">>> Creating namespace ${NAMESPACE}"
kubectl create ns ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
kubectl config set-context --current --namespace=$NAMESPACE

echo ">>> Installing delivery-db from ${DELIVERY_DB_CHART}"
helm upgrade -i delivery-db oci://${DELIVERY_DB_CHART%:*} \
  --namespace ${NAMESPACE} \
  --version ${DELIVERY_DB_CHART#*:} \
  --values ${VALUES_DIR}/values-delivery-db.yaml

echo ">>> Installing delivery-service from ${DELIVERY_SERVICE_CHART}"
helm upgrade -i delivery-service oci://${DELIVERY_SERVICE_CHART%:*} \
  --namespace ${NAMESPACE} \
  --version ${DELIVERY_SERVICE_CHART#*:} \
  --values ${VALUES_DIR}/values-delivery-service.yaml
echo ">>> Waiting for delivery-service to become ready, this can take up to 3 minutes..."
kubectl rollout status deployment delivery-service \
  --namespace ${NAMESPACE} \
  --timeout=180s

echo ">>> Installing delivery-dashboard from ${DELIVERY_DASHBOARD_CHART}"
helm upgrade -i delivery-dashboard oci://${DELIVERY_DASHBOARD_CHART%:*} \
  --namespace ${NAMESPACE} \
  --version ${DELIVERY_DASHBOARD_CHART#*:} \
  --values ${VALUES_DIR}/values-delivery-dashboard.yaml

echo ">>> Installing extensions from ${EXTENSIONS_CHART}"
helm upgrade -i extensions oci://${EXTENSIONS_CHART%:*} \
  --namespace ${NAMESPACE} \
  --version ${EXTENSIONS_CHART#*:} \
  --values ${VALUES_DIR}/values-extensions.yaml
