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
| M1 | Eval harness + full-schema baseline | **Done bar the variance re-run**: baseline scores 46% EX without evidence hints |
| M2 | Offline indexer | **In progress**: FK graph with inferred keys, value index, descriptions, embeddings |
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

### 5. Evaluation

The 50-question sample (`eval/sample_50.json`) is committed and frozen. Build the
gold result cache once, then run a strategy:

```sh
uv run python scripts/cache_gold.py
uv run python scripts/run_eval.py gold_oracle
uv run python scripts/run_eval.py full_schema --limit 3
uv run python scripts/run_eval.py full_schema
```

`full_schema` is the baseline: each question's own database as `CREATE TABLE`
DDL with keys and 3 sample rows, sent to `openai/gpt-oss-120b` on Groq
(`reasoning_effort=medium`, temperature 0, no evidence hints). It needs
`GROQ_API_KEY` in `.env`. It runs within the Groq free tier: requests are paced
to the per-minute token limit, and a run stops with `QuotaExhausted` rather than
waiting out the daily limit. A full 50-question run uses about 150K tokens, so
plan one per day. Use `--limit` for smoke tests.

Each run writes three files to `runs/<timestamp>_<strategy>/`:

- `config.json`: git SHA, sample hash, question ids, price table
- `results.jsonl`: one row per question with SQL, correctness, errors, tokens, latency, cost
- `summary.json`: EX overall and by difficulty, errors by type, tokens, p50/p95 latency, cost

Only `summary.json` is committed. `gold_oracle` returns the gold SQL; it must score 100% EX, which
checks the harness itself.

Compare two runs question by question. With 50 questions each one is worth 2
points, so read the fixed and broken lists, not just the EX delta:

```sh
uv run python scripts/compare.py runs/<run_a> runs/<run_b>
```

## Offline index (M2)

Built once per schema, used by the retriever. No LLM at query time.

```sh
uv run python scripts/describe_schema.py
uv run python scripts/build_index.py
```

`describe_schema.py` writes one table and column description per table with
`gpt-oss-20b`. It is resumable: re-running skips tables whose schema is
unchanged, so a run interrupted by the free-tier daily limit continues the next
day. `build_index.py` then builds everything else and refuses to run while any
table is undescribed:

| Part | What it holds | LLM |
|---|---|---|
| `fk_graph.json` | declared foreign keys plus keys inferred from names and verified against the data | no |
| `values.json` | distinct values of low-cardinality text columns, for keyword lookup | no |
| `descriptions.json` | table and column descriptions, with per-table token cost | yes, offline |
| `chroma/` | embeddings of one document per table and per column (fastembed `bge-small-en-v1.5`, local) | no |
| `manifest.json` | counts, per-part content hashes, a combined content hash, and the offline token cost | — |

Everything lands in `data/index/`, which is gitignored. Descriptions and sampled
values are treated as untrusted text: they are generated from database content
and end up in prompts.

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
  changing its own defaults. Tests pin both; `db.execute` closes them.
- **Single query path, `sqlagent.db.execute`:**
  - SQLGlot accepts exactly one read-only query. It rejects DML hidden in CTEs,
    `SELECT INTO`, `FOR UPDATE`, `SET`, `COPY`, and multiple statements.
  - Each call runs in a `READ ONLY` transaction with its own `statement_timeout`.
  - Results come through a server-side cursor (which also rejects multi-statement
    input at the protocol level), capped at 10,000 rows with a `truncated` flag.
  - Every call, including rejected ones, is appended to `audit/queries.jsonl`.
- **Untrusted prompt data:** sample values are sanitised (whitespace collapsed,
  comment and tag delimiters escaped, truncated) and wrapped in `<schema>` tags
  that the model is told to treat as data. Whatever the model returns still has
  to pass `db.execute`.

`tests/test_security.py` proves each database control by connecting directly as
the role; `tests/test_db.py` covers the query path.

## Repository layout

```
docker-compose.yml         Postgres 16 for local development
sql/00_roles.sql           read-only role and privileges
scripts/                   setup, sample, gold cache, run_eval, compare
src/sqlagent/              config, db (single query path), eval/, index/ (fk graph, values, descriptions, embeddings), strategies/
tests/                     security and unit tests; fixtures/ for CI
eval/                      committed eval artifacts: table → database map, frozen sample
data/  runs/               gitignored: dataset, offline index, run outputs
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
