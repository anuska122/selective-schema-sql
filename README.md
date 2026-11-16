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
honestly** against a strong full-schema baseline.

## Current status

The offline index, hybrid retrieval, selection, generation, validation/repair,
evaluation harness, FastAPI service and Next.js demo are implemented. Recent
maintenance adds strict vector-index checks, generic HTTP errors, request IDs,
mobile navigation, request cancellation, database-list recovery, persistent
single-host worker quotas, and reproducible evaluation settings.

The full **498-question reference cache and gold-oracle check pass at 100%** with
an explicit **50,000-row evaluation cap**. This verifies reference execution and
the harness; it is not a generated-SQL accuracy score. The API still returns at
most 100 rows and the normal database execution default remains 10,000 rows.

**Model benchmarks are blocked:** the currently configured Groq key is rejected
with HTTP 401. Full-schema and selective runs stop as incomplete, with no accuracy
score, and can be resumed after credentials are repaired. Historical scores below
remain unchanged. Browser visual checks are also unavailable in the current
execution environment; mobile behavior is covered by interaction tests.

Latest local verification (2026-11-16): **380 Python tests passed**, **98.77%
coverage**, **54 web tests passed**; Python lint/format checks, web lint/typecheck
and production build passed. The Docker image builds and passes local readiness,
token enforcement and shared-quota checks, including persistence across container
replacement. These are local checks, not remote CI
or proof of a successful model answer.

Implementation status and decisions are maintained in [docs/PLAN.md](docs/PLAN.md)
and [docs/DECISIONS.md](docs/DECISIONS.md).

## Historical model results

Measured on [BIRD Mini-Dev](https://github.com/bird-bench/mini_dev) (PostgreSQL):
**11 databases, 75 tables, 798 columns, 3.9M rows**. Frozen 50-question sample,
no evidence hints, `gpt-oss-120b` generator, `gpt-oss-20b` selector, Groq free
tier. The historical EX metric below uses set equality: the query runs and returns
the same distinct rows as the reference answer, ignoring duplicate counts and row order.
These figures have not been recomputed with the stricter scoring now available.
Each row is one run; read the variance note before comparing two rows.

| Strategy | Tables visible | EX | Input tokens / question | Cost / question | p50 latency |
|---|---|---|---|---|---|
| Full schema (baseline) | own database | 50% | 2,219 | $0.00052 | 1.3s |
| Selective | own database | 46% | 1,425 | $0.00040 | 1.8s |
| Selective + validation | own database | 50% | 1,455 | $0.00039 | 1.8s |
| Selective | all 75 | 46% | 2,021 | $0.00043 | 1.7s |

- **Variance is the headline caveat.** The baseline was run twice with
  byte-identical prompts at temperature 0: 50% and 46%, with 4 questions flipping
  (1 fixed, 3 broken). So roughly 4 points of EX is run-to-run noise, and none of
  the accuracy gaps in the table above are significant on 50 questions. The token
  and cost numbers are stable: both runs averaged exactly 2,219 input tokens.
- **The token saving is the real result:** selective matches the baseline's
  accuracy band at 34% fewer input tokens and 25% lower cost.
- **All 75 tables visible:** selective holds the same accuracy band with every
  table in the corpus as a candidate (46%, 2 questions fixed and 2 broken). The
  full-schema prompt there is 8.2K-21.8K tokens, over the free tier's 8K request
  limit, so the baseline cannot run at all. This is the case selective retrieval
  exists for.
- **A recall-first selector did not pay for itself.** Also keeping the
  retriever's top 4 tables includes the needed tables 98% of the time (vs 82%),
  but costs 57% more tokens and scored 44%, so it buys no measurable accuracy
  with the saving spent. It stays opt-in (`selective_recall`).
- The retriever finds 99.3% of needed tables in its top 30 (all 498 questions,
  all 75 tables visible).
- The repair step ran once in 50 questions and did not change the answer.

Run summaries are in `runs/*/summary.json`. Cost is at Groq list prices; the
actual spend was $0.

## How it works

The schema is indexed once, offline. Each question then walks a short pipeline
where only two steps call a model.

```mermaid
flowchart TD
    Q["Question<br/>&quot;how many superheroes have blue eyes?&quot;"]

    subgraph offline["OFFLINE · rebuilt only when the schema changes"]
        PG[("Postgres<br/>75 tables · 798 columns")]
        PG --> DESC["Descriptions<br/>plain English per table and column,<br/>so a name like cust_typ_cd is findable"]
        PG --> FKG["Foreign-key graph<br/>declared keys + keys inferred<br/>from names and verified on data"]
        PG --> VALS["Value index<br/>distinct values of<br/>low-cardinality columns"]
        DESC --> EMB["Embeddings<br/>ChromaDB, local model"]
    end

    Q --> RET

    subgraph online["ONLINE · per question"]
        RET["1 · Retriever — no LLM<br/>vector + BM25 + value lookup<br/>75 tables → 30 candidates"]
        SEL["2 · Selector — 1 cheap LLM call<br/>cut to the minimal set, then expand<br/>along the FK graph so joins are reachable<br/>30 candidates → 2 tables"]
        GEN["3 · Generator — 1 strong LLM call<br/>SQL against those 2 tables only"]
        VAL{"4 · Validator — no LLM<br/>parses · every column exists · EXPLAIN<br/>read-only"}
        REP["Repair — 1 LLM call<br/>the error is fed back once"]
        WIDE["Widen<br/>add the top 12 candidates<br/>and generate once more"]

        RET --> SEL --> GEN --> VAL
        VAL -->|"invalid"| REP --> VAL
        VAL -->|"invalid again"| WIDE
    end

    EMB -.->|"semantic match"| RET
    VALS -.->|"'blue' is a value,<br/>not a column"| RET
    FKG -.->|"join paths"| SEL

    VAL -->|"valid"| EXEC["Read-only execution<br/>SELECT only · 10s timeout · 10k row cap · audited"]
    WIDE --> EXEC
    EXEC --> ANS["234"]
```

That is the real trace for that question: 75 tables went in, 2 reached the
prompt, 2 model calls were made, and the answer was correct. The retriever and
validator use no model at all — retrieval is vectors and keywords, join
resolution is graph traversal, validation is a parser and `EXPLAIN`. If the final
widened query still fails validation, the pipeline returns no SQL for execution. A question therefore costs two LLM calls, three if a repair is needed, and four in the
worst case where the schema is widened.

## Local setup

**Requirements:** Docker, [uv](https://docs.astral.sh/uv/), ~4 GB free disk.

### 1. Secrets

Create a `.env` in the repo root. It is gitignored; never commit it.
[.env.example](.env.example) lists the available backend settings;
[web/.env.example](web/.env.example) lists the web server settings.

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

Strategies: `gold_oracle` (harness check), `full_schema` (baseline), `selective`,
`selective_validated`, `selective_pooled` (all 75 tables visible) and
`selective_recall` (recall-first selector).

Each run writes three files to `runs/<timestamp>_<strategy>/`:

- `config.json`: git SHA, sample hash, question ids, price table
- `results.jsonl`: one row per question with SQL, correctness, errors, tokens, latency, cost
- `summary.json`: EX overall and by difficulty, errors by type, tokens, p50/p95 latency, cost

Only `summary.json` is committed. `gold_oracle` returns the gold SQL; it must score 100% EX, which
checks the harness itself.

Compare two runs question by question. Repeating one identical run flipped 4
questions, so read the fixed and broken lists, not just the EX delta:

```sh
uv run python scripts/compare.py runs/<run_a> runs/<run_b>
```

A run stopped by the free-tier daily limit is marked incomplete; continue it the
next day instead of starting over (it refuses if the strategy, its settings or
the questions changed):

```sh
uv run python scripts/run_eval.py selective_pooled --resume runs/<run>
```

The Results table above is generated from run summaries, not typed by hand:

```sh
uv run python scripts/results_table.py runs/<run_a> runs/<run_b> ...
```

### Scoring and larger evaluations

New evaluation runs default to `--comparison multiset`: duplicate counts matter,
while row order is ignored. Use `--comparison ordered` when row order is part of
the task, or `--comparison set` to reproduce the historical table above. These
are project metrics, not a claim of official BIRD evaluator equivalence. Scoring
mode is saved in run configuration and summaries; resume, comparison and table
export reject mixed modes. Comparison and table export also reject different row
limits. New runs fingerprint question contents so resume detects changed text or SQL. To resume a historical run, explicitly pass `--comparison set`.

The frozen 50-question sample remains unchanged. To evaluate beyond it without
silently changing the sample, first cache reference results for the full dataset:

```sh
uv run python scripts/cache_gold.py --all --max-rows 50000
uv run python scripts/run_eval.py gold_oracle --all --max-rows 50000
uv run python scripts/run_eval.py full_schema --all --max-rows 50000
uv run python scripts/run_eval.py selective_validated --all --max-rows 50000
```

The full cache is `data/gold/all.json`, with its row cap recorded in
`data/gold/all.meta.json`. `--gold-cache` selects another cache for `run_eval.py`,
and `cache_gold.py --output` selects its output. Both commands must use the same
`--max-rows` value. The CLI bounds evaluation caps to 1–1,000,000 rows; requests
remain read-only and retain the database statement timeout.

Question IDs 340, 346 and 397 return 25,061, 29,936 and 11,446 reference rows.
The explicit 50,000-row evaluation policy covers them without excluding any
questions or raising the public API limit. Cache creation makes no model calls
and refuses to write if a reference query fails or remains truncated.

Provider authentication, network and exhausted retry failures stop model runs
as **incomplete**, rather than recording hundreds of wrong answers. The CLI
returns exit code 2 for an incomplete run. Table export and error analysis reject
incomplete runs. After repairing credentials, resume the recorded runs:

```sh
uv run python scripts/run_eval.py full_schema --all --max-rows 50000 \
  --resume runs/20261116T080351Z_full_schema
uv run python scripts/run_eval.py selective_validated --all --max-rows 50000 \
  --resume runs/20261116T080356Z_selective_validated
```

Run error analysis after a completed evaluation:

```sh
uv run python scripts/analyze_errors.py runs/<completed-run>
```

It groups failures into possible retrieval misses, selection misses, missing or
invalid SQL, execution errors, and wrong results. These are diagnostic heuristics
based on the reference query's tables, not proof of causality. New selective
traces retain the full retrieved table list; historical top-ten candidate lists
cannot establish a retrieval miss. On the historical validated 50-question run,
this check finds 25 correct answers, 6 possible selection misses and 19 other
wrong results. Repeat paired runs under identical settings before making an
accuracy-improvement claim. Model runs consume provider quota.

### Web demo

```sh
cd web
npm ci
cp .env.example .env.local
npm run dev
```

Set `BACKEND_URL` to the API address. For a token-protected backend, set the web
server's `API_TOKEN` to the same value as `SQLAGENT_API_TOKEN`; never expose it in
a `NEXT_PUBLIC_` variable. Database selection and saved questions are accessible
from the navigation menu on mobile as well as the desktop sidebar. Questions
are independent requests: saved history is not sent as model conversation context.

The composer offers **Cancel request** while waiting. Cancellation aborts the
browser request and propagates to the web proxy; a model or database operation
already running on the API may still finish and consume quota. Database-list
failures show a retry action. Mobile navigation exposes databases and history,
and reopening a saved question restores its database selection.

### Quotas and proxy trust

The web server keeps an additional rolling per-client limit in memory
(`RATE_LIMIT_PER_HOUR`, default 5). It ignores forwarded IP headers unless
`TRUST_PROXY_HEADERS=1`. Enable this only behind a proxy that replaces incoming
client IP headers; otherwise all visitors intentionally share an anonymous bucket.
The web proxy hashes the client identifier before forwarding it to the API.

Set `SQLAGENT_LIMIT_DB` to enable SQLite-backed API quotas shared by workers using
the same file. Reservations are atomic; rejected hourly requests do not spend
the daily budget. The daily limit defaults to 100 (`SQLAGENT_DAILY_QUESTIONS`);
the per-client limit defaults to 5 per UTC clock hour
(`SQLAGENT_HOURLY_QUESTIONS`). Client identifiers are trusted only with a configured
shared API token; unauthenticated direct callers share a bucket. Requests reserve
quota before model execution, including requests that later fail or are cancelled.

Without `SQLAGENT_LIMIT_DB`, the API retains its local in-memory daily counter.
The Docker image enables SQLite by default at `/home/user/quota/limits.sqlite3`.
Mount `/home/user/quota` on a persistent volume to preserve quotas across container
replacement. This supports workers on one host sharing a local SQLite file;
separate hosts require a central quota service. SQLite on a network filesystem
is not a supported substitute.

## Offline index

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

Everything lands in `data/index/`, which is gitignored. Loading refuses a missing,
empty, incomplete or stale vector collection. Stored documents and metadata must
match `documents.json`, database mappings must agree, and a present manifest must
match the embedding model, documents, values and foreign-key graph. Loading never
creates a replacement empty collection. Descriptions and sampled
values are treated as untrusted text: they are generated from database content
and end up in prompts.

## API

```sh
uv run uvicorn sqlagent.api.app:app --port 8000
curl -s localhost:8000/health
curl -s localhost:8000/ask -H 'content-type: application/json' \
  -d '{"question": "how many superheroes have blue eyes?"}'
```

`POST /ask` runs retrieve → select → generate → validate → repair and returns
the SQL, up to 100 result rows, and the per-stage trace (calls, tokens,
latency, which rung was reached). The offline index must be built first, and
`GROQ_API_KEY` must be set. Results come back through the same read-only,
audited query path as everything else. The API supports a shared token through `SQLAGENT_API_TOKEN`; when it is unset,
`/ask` is unauthenticated and should stay local. `/health` is a lightweight liveness
probe. Use `/ready` for readiness: it initializes the pipeline and checks the
read-only database connection, returning 503 with a generic error on failure.
The readiness probe does not make a model request or test provider credentials
or quota. A valid `/ready` response therefore cannot establish that Groq will
accept a request. API responses include a `request_id` that also links SQL
validation and execution audit records.

## Local deployment verification

The Docker bundle includes PostgreSQL, the public BIRD dataset, the offline index
and the API. It does not include the Next.js web server. Build the bundle in a
separate directory so local `.env` files are never copied into the image:

```sh
deploy/assemble.sh /tmp/sqlagent-bundle
docker build -f deploy/Dockerfile -t sqlagent:local /tmp/sqlagent-bundle
```

Export `GROQ_API_KEY` and a strong `SQLAGENT_API_TOKEN` in your shell, then run:

```sh
docker run --name sqlagent-demo \
  -p 127.0.0.1:7860:7860 \
  -e GROQ_API_KEY -e SQLAGENT_API_TOKEN \
  -v sqlagent-quota:/home/user/quota \
  sqlagent:local
```

The entrypoint refuses missing credentials, generates a fresh read-only database
password and keeps PostgreSQL listening on loopback inside the container. Docker
health checks use `/ready`. `/health` and `/ready` are public probes; `/ask`
requires the token. A rejected provider key still allows readiness because no
provider call is made by that probe. Keep the binding local for verification;
configure TLS, proxy trust and the server-only web token before public hosting.

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
- **API and web app:** errors returned to clients are generic; details go to
  the server log only. The web routes cap request bodies at 16 KB and send a
  content security policy, HSTS, `nosniff`, `frame-ancestors 'none'` and
  `no-referrer`.
- **Serving it publicly:** the API checks that it is connected as
  `sqlagent_ro` with no write privileges before initializing the query service.
  Configure your deployment to probe `/ready` before routing question traffic. `SQLAGENT_API_TOKEN` makes it answer
  only callers that present that token, so it can sit behind the web app without
  being usable directly; `SQLAGENT_DAILY_QUESTIONS` caps questions per day and
  `SQLAGENT_PAUSED=1` stops it entirely. The web layer adds a per-IP hourly limit
  (`RATE_LIMIT_PER_HOUR`). Together these bound what a visitor can spend of the
  model quota.
- **Accepted risks:** there is no per-user authentication, so anyone with the
  link can ask questions until the caps are reached. A visitor can make the model
  run any `SELECT` over the demo databases, which is only acceptable because the
  role cannot write and BIRD is public data — never point this at a private
  database. ChromaDB has open advisories that affect its server mode only; it
  runs embedded here, so never start `chroma run`.

`tests/test_security.py` proves each database control by connecting directly as
the role; `tests/test_db.py` covers the query path.

## Repository layout

```
docker-compose.yml         Postgres 16 for local development
sql/00_roles.sql           read-only role and privileges
scripts/                   setup, sample, gold cache, run_eval, compare
src/sqlagent/              config, db, generation, eval/, index/, retrieval/, selection/, validation/, strategies/, api/
web/                       Next.js + TypeScript frontend
tests/                     security and unit tests; fixtures/ for CI
eval/                      committed eval artifacts: table → database map, frozen sample
data/  runs/               gitignored: dataset, offline index, run outputs
```
