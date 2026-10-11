#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
pushd ../../03-resource-tenant-isolation/code >/dev/null
bash scripts/check.sh
docker compose build api checks
popd >/dev/null
docker compose --profile tools build checks mcp
docker compose --profile tools run --rm --no-deps checks
docker compose up -d --wait opa
docker compose run --rm -T --no-deps mcp python /app/scripts/smoke.py --container