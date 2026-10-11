#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
pushd ../../03-resource-tenant-isolation/code >/dev/null
bash scripts/run.sh
popd >/dev/null
docker compose build mcp
docker compose up -d --wait opa
docker compose run --rm -T mcp