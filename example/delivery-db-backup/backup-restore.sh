#!/usr/bin/env bash

set -eu

REGISTRY=""
NAME=""
VERSION=""

parse_flags() {
  while test $# -gt 0; do
    case "$1" in
    --registry)
      shift; REGISTRY="$1"
      ;;
    --name)
      shift; NAME="$1"
      ;;
    --version)
      shift; VERSION="$1"
      ;;
    --pgpassword)
      shift; PGPASSWORD="$1"
      ;;
    esac

    shift
  done
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
check_required_flags REGISTRY NAME VERSION PGPASSWORD

ocm download resources \
  -O delivery-db-backup \
  OCIRegistry::${REGISTRY}//${NAME}:${VERSION} \
  delivery-db-backup

kubectl port-forward delivery-db-0 5431:5432 > /dev/null &
sleep 3 # wait for port-forwarding to be initialised

pg_restore -h localhost -p 5431 -U postgres -d postgres -cv delivery-db-backup

rm delivery-db-backup
