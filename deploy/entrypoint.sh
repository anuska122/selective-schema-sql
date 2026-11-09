#!/usr/bin/env bash
set -euo pipefail

export SQLAGENT_RO_PASSWORD="$(openssl rand -hex 24)"

pg_ctl -D "$PGDATA" -o "-c listen_addresses=127.0.0.1 -k /tmp" -w start
psql -U user -q -d bird -v ON_ERROR_STOP=1 -v ro_password="$SQLAGENT_RO_PASSWORD" \
    -f /home/user/app/sql/00_roles.sql

exec uv run --frozen --no-dev uvicorn sqlagent.api.app:app \
    --host 0.0.0.0 --port "${PORT:-7860}" --timeout-keep-alive 75
