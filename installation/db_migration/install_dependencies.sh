#!/usr/bin/env bash

set -eu

own_dir="$(readlink -f "$(dirname "${BASH_SOURCE[0]}")")"

if ! which pip3 &> /dev/null; then
  echo "pip3 is required"
  exit 1
fi

if ! which apk 1>/dev/null; then
  echo "apk is required"
  exit 1
fi

if ! which psql 1>/dev/null; then
  echo ">>> Installing postgresql-client..."
  apk add postgresql-client
  echo ">>> Installed postgresql-client in version $(psql --version)"
fi

pip3 install --no-cache --upgrade -r "${own_dir}/requirements.txt"
