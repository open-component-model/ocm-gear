#!/usr/bin/env bash

set -euo pipefail

OWN_DIR=$(readlink -f "$(dirname "${0}")")

CFG_DIR=""
CFG_SET=""
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
    gardener-ci config export_kubeconfig --kubernetes-config-name ${KUBERNETES_CFG_NAME} --output-file "${OWN_DIR}/kubeconfig.yaml"
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

OCM_REPO="europe-docker.pkg.dev/gardener-project/releases"
OCM_GEAR_COMPONENT="ocm.software/ocm-gear"
OCM_GEAR_COMPONENT_REF="${OCM_REPO}//${OCM_GEAR_COMPONENT}"
OCM_GEAR_VERSION="${OCM_GEAR_VERSION:-$(ocm show versions ${OCM_GEAR_COMPONENT_REF} | tail -1)}"
COMPONENT_DESCRIPTORS=$(ocm get cv ${OCM_GEAR_COMPONENT_REF}:${OCM_GEAR_VERSION} -o yaml -r)

echo ">>> Installing required Python packages"
PKG_DIR="/tmp/site-packages"
mkdir -p "${PKG_DIR}"

CC_UTILS_VERSION=$(echo "${COMPONENT_DESCRIPTORS}" | yq eval '.component | select(.name == "github.com/gardener/cc-utils") | .version')
for resource in gardener-cicd-libs gardener-oci gardener-ocm; do
  echo "   >>> Downloading ${resource}:${CC_UTILS_VERSION}"
  ocm download resources \
    "${OCM_REPO}//github.com/gardener/cc-utils:${CC_UTILS_VERSION}" \
    "${resource}" \
    -O - | tar xJ -C "${PKG_DIR}"
done

DELIVERY_SERVICE_VERSION=$(echo "${COMPONENT_DESCRIPTORS}" | yq eval '.component | select(.name == "ocm.software/ocm-gear/delivery-service") | .version')
for resource in delivery-gear-utils; do
  echo "   >>> Downloading ${resource}:${DELIVERY_SERVICE_VERSION}"
  ocm download resources \
    "${OCM_REPO}//ocm.software/ocm-gear/delivery-service:${DELIVERY_SERVICE_VERSION}" \
    "${resource}" \
    -O - | tar xJ -C "${PKG_DIR}"
done

pip3 install --upgrade --find-links "${PKG_DIR}" -r ${OWN_DIR}/requirements.txt

rm -rf "${PKG_DIR}"

echo ">>> Installing OCM-Gear in version ${OCM_GEAR_VERSION}"

BOOTSTRAPPING_CHART=$(echo "${COMPONENT_DESCRIPTORS}" | yq eval '.component.resources.[] | select(.name == "bootstrapping" and .type | test("helmChart")) | .access.imageReference')
DELIVERY_SERVICE_CHART=$(echo "${COMPONENT_DESCRIPTORS}" | yq eval '.component.resources.[] | select(.name == "delivery-service" and .type | test("helmChart")) | .access.imageReference')
DELIVERY_DASHBOARD_CHART=$(echo "${COMPONENT_DESCRIPTORS}" | yq eval '.component.resources.[] | select(.name == "delivery-dashboard" and .type | test("helmChart")) | .access.imageReference')
EXTENSIONS_CHART=$(echo "${COMPONENT_DESCRIPTORS}" | yq eval '.component.resources.[] | select(.name == "extensions" and .type | test("helmChart")) | .access.imageReference')
DELIVERY_DATABASE_CHART=$(echo "${COMPONENT_DESCRIPTORS}" | yq eval '.component.resources.[] | select(.name == "postgresql" and .type | test("helmChart")) | .access.imageReference')
PROMETHEUS_OPERATOR_CHART=$(echo "${COMPONENT_DESCRIPTORS}" | yq eval '.component.resources.[] | select(.name == "prometheus-operator" and .type | test("helmChart")) | .access.imageReference')

if [ ! -d "${VALUES_DIR}" ]; then
  echo ">>> Generating required helm values into ${VALUES_DIR}"
  python3 ${OWN_DIR}/generate_helm_values.py \
    ${CFG_DIR:+"--cfg-dir"} ${CFG_DIR:+${CFG_DIR}} \
    ${CFG_SET:+"--cfg-set"} ${CFG_SET:+${CFG_SET}} \
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
    --set externalTrafficPolicy=Cluster \
    --set controller.metrics.enabled=true \
    --set-string controller.podAnnotations."prometheus\.io/scrape"="true" \
    --set-string controller.podAnnotations."prometheus\.io/port"="10254"
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

if [ -f "${VALUES_DIR}/values-bootstrapping.yaml" ]; then
  echo ">>> Installing bootstrapping chart from ${BOOTSTRAPPING_CHART}"
  helm upgrade -i bootstrapping oci://${BOOTSTRAPPING_CHART%:*} \
    --namespace ${NAMESPACE} \
    --version ${BOOTSTRAPPING_CHART#*:} \
    --values ${VALUES_DIR}/values-bootstrapping.yaml
fi

echo ">>> Installing delivery-database from ${DELIVERY_DATABASE_CHART}"
helm upgrade -i delivery-db oci://${DELIVERY_DATABASE_CHART%:*} \
  --namespace ${NAMESPACE} \
  --version ${DELIVERY_DATABASE_CHART#*:} \
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

if [ -f "${VALUES_DIR}/values-prometheus-operator.yaml" ]; then
  echo ">>> Installing prometheus-operator crds"
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
  helm repo update
  helm upgrade -i prometheus-operator-crds prometheus-community/prometheus-operator-crds

  echo ">>> Installing prometheus-operator from ${PROMETHEUS_OPERATOR_CHART}"
  helm upgrade -i prometheus-operator oci://${PROMETHEUS_OPERATOR_CHART%:*} \
    --namespace ${NAMESPACE} \
    --version ${PROMETHEUS_OPERATOR_CHART#*:} \
    --values ${VALUES_DIR}/values-prometheus-operator.yaml

  if [ -n "${INSTALL_INGRESS_CONTROLLER}" ]; then
    echo ">>> Creating service monitor for ingress nginx controller"
    echo "apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: ingress-nginx
  labels:
    app: prometheus
spec:
  selector:
    matchLabels:
      app.kubernetes.io/name: ingress-nginx
  endpoints:
    - port: metrics
      interval: 15s" | kubectl apply --namespace=${INGRESS_NAMESPACE} -f -
  fi
fi

echo ">>> Going to attempt db-migration (if necessary)"
PGPASSWORD=$(cat ${VALUES_DIR}/values-delivery-db.yaml | yq .postgresqlPassword)
kubectl port-forward delivery-db-0 5430:5432 --namespace ${NAMESPACE} > /dev/null &
${OWN_DIR}/db_migration/migrate.sh --pgpassword ${PGPASSWORD}
