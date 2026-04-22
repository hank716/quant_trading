#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose -f compose/docker-compose.yml up -d quant-ui
echo "Services started:"
echo "  UI: http://localhost:8501"
