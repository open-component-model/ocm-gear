#!/usr/bin/env bash

set -eu

own_dir="$(readlink -f "$(dirname "${BASH_SOURCE[0]}")")"

HOST="localhost"
PORT="5430"
DATABASE="postgres"
PGUSER="postgres"
PGPASSWORD=""

parse_flags() {
  while test $# -gt 0; do
    case "$1" in
    --host)
      shift; HOST="$1"
      ;;
    --port)
      shift; PORT="$1"
      ;;
    --database)
      shift; DATABASE="$1"
      ;;
    --pguser)
      shift; PGUSER="$1"
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
check_required_flags HOST PORT DATABASE PGUSER PGPASSWORD

${own_dir}/install_dependencies.sh

id_datatype=$(PGPASSWORD=${PGPASSWORD} psql \
  -h $HOST \
  -p $PORT \
  -d $DATABASE \
  -U $PGUSER \
  -t \
  -c "SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'artefact_metadata' AND COLUMN_NAME = 'id';" | xargs)

if [[ $id_datatype != "character" ]]; then
  PGPASSWORD=${PGPASSWORD} \
    psql -h $HOST -p $PORT -d $DATABASE -U $PGUSER -a -f ${own_dir}/_migrate_1.sql

  ${own_dir}/_migrate_2.py --db-url "postgresql+psycopg://${PGUSER}:${PGPASSWORD}@${HOST}:${PORT}/${DATABASE}"

  PGPASSWORD=${PGPASSWORD} \
    psql -h $HOST -p $PORT -d $DATABASE -U $PGUSER -a -f ${own_dir}/_migrate_3.sql
fi
