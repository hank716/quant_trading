$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent | Split-Path -Parent)
docker compose -f compose/docker-compose.yml up -d quant-ui prometheus grafana
Write-Host "Services started:"
Write-Host "  UI:         http://localhost:8501"
Write-Host "  Prometheus: http://localhost:9090"
Write-Host "  Grafana:    http://localhost:3000 (admin/admin)"
