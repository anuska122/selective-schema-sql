#!/usr/bin/env bash
# Apply sql/00_roles.sql as the admin role. Safe to run repeatedly.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
: "${SQLAGENT_RO_PASSWORD:?set SQLAGENT_RO_PASSWORD in .env}"

docker compose exec -T postgres \
  psql -q -U postgres -d bird -v ro_password="$SQLAGENT_RO_PASSWORD" -f - < sql/00_roles.sql
echo "roles applied"
