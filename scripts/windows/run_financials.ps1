Set-Location (Split-Path $PSScriptRoot -Parent | Split-Path -Parent)
docker compose -f compose/docker-compose.yml --profile jobs run --rm quant-financials
