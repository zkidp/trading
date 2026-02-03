#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PHASE="${1:-preopen}"

# Run one-off container invocation for the given phase.
# Uses .env and overrides RUN_PHASE.
docker compose run --rm \
  -e RUN_PHASE="$PHASE" \
  app
