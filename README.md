# Selective-Schema Text-to-SQL

A text-to-SQL system that **does not paste the whole database schema into the
prompt**. It indexes the schema offline, retrieves only the tables and columns
relevant to each question, and generates SQL against that small subset.

## Why

On large databases, putting the full schema in the prompt is the bottleneck:

- **Cost:** every question pays for thousands of schema tokens.
- **Context limits:** real warehouses don't fit.
- **Accuracy:** too much schema makes the model pick the wrong table.

Selective retrieval should beat full-schema prompting on all three. This is a
known research area (schema linking, database context compression; see e.g.
CHESS, CRUSH4SQL, and the counter-argument "The Death of Schema Linking?").
The goal here isn't novelty. It's a working implementation, **measured
honestly** against a strong full-schema baseline on the
[BIRD Mini-Dev](https://github.com/bird-bench/mini_dev) benchmark (PostgreSQL version).

## Architecture

```
OFFLINE (rebuilt when the schema changes)
  describe + embed every table/column · foreign-key graph · value index · table templates

ONLINE (per question)
  1. Retriever   no LLM    hybrid vector + BM25 → ~30-50 candidate tables   (metric: recall)
  2. Selector    1 cheap LLM call → minimal set, expanded along FK graph
  3. Generator   1 strong LLM call over the small schema subset
  4. Validator   no LLM first: SQLGlot parse, EXPLAIN, column checks, read-only check
                 → repair call only on failure → widen schema after two failed repairs
```

Design rules:

- A stage that doesn't need an LLM must not use one.
- Any added LLM call must earn its place with a measured accuracy gain.
- No feature lands without a before/after benchmark number.

## Status

| Milestone | Scope | State |
|---|---|---|
| M1 | Eval harness + full-schema baseline | **In progress**: data loaded, read-only role, security tests, CI |
| M2 | Offline indexer | Not started |
| M3 | Retriever, measuring schema-linking recall (go/no-go) | Not started |
| M4 | Selector | Not started |
| M5 | Validator + escalation ladder | Not started |
| M6 | Observability, then FastAPI | Not started |

Work is tracked in GitHub issues, one per task, grouped by milestone.
Architectural decisions are issues labelled `decision`.

## Local setup

**Requirements:** Docker, [uv](https://docs.astral.sh/uv/), ~4 GB free disk.

### 1. Secrets

Create a `.env` in the repo root. It is gitignored; never commit it.

```sh
cat > .env <<EOF
POSTGRES_ADMIN_PASSWORD=$(openssl rand -hex 16)
SQLAGENT_RO_PASSWORD=$(openssl rand -hex 16)
EOF
```

### 2. Postgres and the BIRD data

```sh
mkdir -p data && curl -o data/minidev.zip https://bird-bench.oss-cn-beijing.aliyuncs.com/minidev.zip
unzip -q data/minidev.zip -d data

docker compose up -d --wait

docker compose exec -T postgres bash -c \
  "sed '/ OWNER TO xiaolongli;\$/d' /data/minidev/MINIDEV_postgresql/BIRD_dev.sql \
   | psql -q -U postgres -d bird -v ON_ERROR_STOP=1 --single-transaction"

uv sync
uv run python scripts/map_tables.py
```

### 3. Read-only role

```sh
scripts/apply_roles.sh
```

### 4. Tests

```sh
uv run pytest
uv run ruff check && uv run ruff format --check
```

Database tests skip when Postgres isn't reachable locally. In CI they fail instead.

## Security model

All generated SQL is treated as untrusted. The controls sit in the database, not
in the prompt.

- **Read-only role `sqlagent_ro`:** CONNECT on `bird` only, SELECT on the
  allowlisted schema only, no sequence privileges. Privileges are the real
  control; `default_transaction_read_only` is a second layer.
- **Default-Postgres bypasses closed:** large-object writes, `set_config` from
  inside a SELECT, DO blocks, TEMP tables, and CONNECT to other databases.
- **Resource limits:** 10s statement timeout, 30s idle-in-transaction timeout,
  100 MB temp files.
- **Known gaps Postgres cannot close:** a bare `SET statement_timeout`, and a role
  changing its own defaults. Tests pin both. The single query path
  (`db.execute`, planned) must accept exactly one SELECT and set limits on every call.
- **Planned (M1–M5):** every query parsed and validated before execution, and a
  full audit log of question, SQL, and result size. Retrieved schema descriptions
  and sampled values are handled as untrusted, since they are a prompt-injection surface.

`tests/test_security.py` proves each control by connecting directly as the role.

## Repository layout

```
docker-compose.yml         Postgres 16 for local development
sql/00_roles.sql           read-only role and privileges
scripts/                   setup: apply roles, verify data load
src/sqlagent/              the package (config so far)
tests/                     security and unit tests; fixtures/ for CI
eval/                      committed eval artifacts (table → database map)
data/  runs/               gitignored: dataset, run outputs
```

## Contributing

- **Issues first:** one issue per task, under its milestone.
- **Branches:** `feature/<ticket-or-scope>` or `bugfix/<ticket-or-scope>`, e.g.
  `feature/23-ci`. Branch from `main`; open the PR against `main`.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org/), e.g.
  `feat(security): add read-only role`, `test(config): ...`, `ci: ...`, `docs: ...`.
- **Never commit** secrets, `.env`, datasets, build or coverage output, or
  unrelated changes.
- **Definition of done:** implementation, tests, coverage, documentation, API
  documentation, security review, and all relevant CI checks complete and
  passing. The PR template has the checklist.

CI runs on every PR: lint and format, lockfile check, security tests against a
real Postgres with coverage enforced, and a gitleaks secret scan.
