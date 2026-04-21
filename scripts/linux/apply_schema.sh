#!/usr/bin/env bash
# Apply Supabase schema. Requires psql and DATABASE_URL env var.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCHEMA_FILE="$SCRIPT_DIR/../../src/database/schema.sql"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "ERROR: DATABASE_URL is not set." >&2
  echo "  Export it first: export DATABASE_URL=postgresql://user:pass@host:5432/db" >&2
  exit 1
fi

if ! command -v psql &>/dev/null; then
  echo "ERROR: psql not found. Install postgresql-client." >&2
  exit 1
fi

echo "Applying schema: $SCHEMA_FILE"
psql "$DATABASE_URL" -f "$SCHEMA_FILE"
echo "Done."
