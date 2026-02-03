#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose run --rm \
  -e RUN_PHASE=monitor \
  app-lite
