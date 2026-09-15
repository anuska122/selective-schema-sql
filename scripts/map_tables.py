"""M1-S1: map every Postgres table to its BIRD db_id and verify the load.

Source of truth for membership is dev_tables.json; the SQLite files give the
reference row counts. Writes eval/table_db_map.json. Exits non-zero on any
mismatch.

Runs as the admin role: this is a one-off setup check, not agent code, so it
deliberately does not go through db.execute().
"""

import json
import os
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MINIDEV = ROOT / "data" / "minidev" / "MINIDEV"
OUT = ROOT / "eval" / "table_db_map.json"


def load_env() -> None:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def sqlite_row_count(db_id: str, table: str) -> int:
    path = MINIDEV / "dev_databases" / db_id / f"{db_id}.sqlite"
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as con:
        return con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]


def main() -> int:
    load_env()
    errors: list[str] = []

    # Expected membership, lowercased to match Postgres identifiers.
    table_to_db: dict[str, str] = {}
    original_name: dict[str, str] = {}
    for db in json.loads((MINIDEV / "dev_tables.json").read_text()):
        for name in db["table_names_original"]:
            key = name.lower()
            if key in table_to_db:
                errors.append(f"collision: {key} in {table_to_db[key]} and {db['db_id']}")
            table_to_db[key] = db["db_id"]
            original_name[key] = name

    dsn = (
        f"host=127.0.0.1 port=5434 dbname=bird user=postgres "
        f"password={os.environ['POSTGRES_ADMIN_PASSWORD']}"
    )
    with psycopg.connect(dsn) as con:
        pg_tables = {
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
        }
        for t in sorted(pg_tables - table_to_db.keys()):
            errors.append(f"in Postgres but not in dev_tables.json: {t}")
        for t in sorted(table_to_db.keys() - pg_tables):
            errors.append(f"in dev_tables.json but not in Postgres: {t}")

        mapping: dict[str, dict[str, int]] = defaultdict(dict)
        for table in sorted(table_to_db.keys() & pg_tables):
            db_id = table_to_db[table]
            pg_count = con.execute(f'SELECT COUNT(*) FROM public."{table}"').fetchone()[0]
            sq_count = sqlite_row_count(db_id, original_name[table])
            if pg_count != sq_count:
                errors.append(f"row count {db_id}.{table}: postgres={pg_count} sqlite={sq_count}")
            mapping[db_id][table] = pg_count

    # Case-insensitive near-collisions (card/cards, race/races) are what make
    # the pooled setup hard; list them so they're visible, not errors.
    near = sorted(
        (a, b)
        for a in table_to_db
        for b in table_to_db
        if a < b and table_to_db[a] != table_to_db[b] and (a + "s" == b or b + "s" == a)
    )

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "source": "BIRD Mini-Dev, MINIDEV/dev_tables.json + MINIDEV_postgresql/BIRD_dev.sql",
                "schema": "public",
                "databases": {db: mapping[db] for db in sorted(mapping)},
                "table_to_db": {t: table_to_db[t] for t in sorted(table_to_db)},
            },
            indent=2,
        )
        + "\n"
    )

    print(f"{len(pg_tables)} tables in Postgres, {len(table_to_db)} expected, {len(mapping)} databases")
    for db in sorted(mapping):
        print(f"  {db:26s} {len(mapping[db]):3d} tables {sum(mapping[db].values()):>10,d} rows")
    print("near-collisions across databases:", ", ".join(f"{a}/{b}" for a, b in near) or "none")
    if errors:
        print(f"\nFAILED with {len(errors)} error(s):")
        for e in errors:
            print("  " + e)
        return 1
    print(f"\nOK: wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
