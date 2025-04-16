#!/usr/bin/env bash

set -euo pipefail

OWN_DIR=$(readlink -f "$(dirname "${0}")")

CFG_DIR="${OWN_DIR}/cfg"
CFG_SET="ocm_gear"
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

parse_flags "$@"

if ! which ocm 1>/dev/null; then
  echo ">>> Installing OCM cli..."
  curl -s https://ocm.software/install.sh | bash
  echo ">>> Installed OCM cli in version $(ocm version)"
fi

OCM_GEAR_COMPONENT_REF="europe-docker.pkg.dev/gardener-project/releases//ocm.software/ocm-gear"
OCM_GEAR_VERSION="${OCM_GEAR_VERSION:-$(ocm show versions ${OCM_GEAR_COMPONENT_REF} | tail -1)}"

echo ">>> Installing OCM-Gear in version ${OCM_GEAR_VERSION}"

ocm download resources ${OCM_GEAR_COMPONENT_REF}:${OCM_GEAR_VERSION} installation -O "${OWN_DIR}/resource-installation"
tar -xzf "${OWN_DIR}/resource-installation"

${OWN_DIR}/installation/install.sh \
  ${CFG_DIR:+"--cfg-dir"} ${CFG_DIR:+${CFG_DIR}} \
  ${CFG_SET:+"--cfg-set"} ${CFG_SET:+${CFG_SET}} \
  ${INGRESS_NAMESPACE:+"--ingress-namespace"} ${INGRESS_NAMESPACE:+${INGRESS_NAMESPACE}} \
  ${INSTALL_INGRESS_CONTROLLER:+"--install-ingress-controller"} \
  ${KUBECONFIG:+"--kubeconfig"} ${KUBECONFIG:+${KUBECONFIG}} \
  ${KUBERNETES_CFG_NAME:+"--kubernetes-cfg-name"} ${KUBERNETES_CFG_NAME:+${KUBERNETES_CFG_NAME}} \
  ${NAMESPACE:+"--namespace"} ${NAMESPACE:+${NAMESPACE}} \
  ${VALUES_DIR:+"--values-dir"} ${VALUES_DIR:+${VALUES_DIR}} \
  ${OCM_GEAR_VERSION:+"--version"} ${OCM_GEAR_VERSION:+${OCM_GEAR_VERSION}}

rm "${OWN_DIR}/resource-installation"
rm -r "${OWN_DIR}/installation"
rm -r "${VALUES_DIR}"
