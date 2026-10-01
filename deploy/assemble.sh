#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out="${1:?usage: assemble.sh <target-dir>}"

mkdir -p "$out/deploy" "$out/eval" "$out/sql" "$out/src" "$out/data"
cp "$root/pyproject.toml" "$root/uv.lock" "$out/"
cp "$root/deploy/Dockerfile" "$root/deploy/entrypoint.sh" "$out/deploy/"
cp "$root/deploy/README.space.md" "$out/README.md"
cp "$root/eval/table_db_map.json" "$out/eval/"
cp "$root/sql/00_roles.sql" "$out/sql/"
rm -rf "$out/src/sqlagent" "$out/data/index"
cp -R "$root/src/sqlagent" "$out/src/"
cp -R "$root/data/index" "$out/data/"
find "$out/src" -name __pycache__ -type d -prune -exec rm -rf {} +

if [ ! -f "$out/bird.dump" ]; then
    docker compose -f "$root/docker-compose.yml" exec -T postgres \
        pg_dump -U postgres -d bird -Fc -Z 9 > "$out/bird.dump"
fi

du -sh "$out"
