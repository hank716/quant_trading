$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent | Split-Path -Parent)
docker compose -f compose/docker-compose.yml down
Write-Host "All services stopped."
