#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
docker compose -f compose/docker-compose.yml up -d quant-ui prometheus grafana
echo "Services started:"
echo "  UI:         http://localhost:8501"
echo "  Prometheus: http://localhost:9090"
echo "  Grafana:    http://localhost:3000 (admin/admin)"
