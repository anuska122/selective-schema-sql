# Plan

**Status:** M1-S1 done (2026-09-15). **Next session:** M1-S2 — decide D6 first.

M1-S1 notes: Postgres 16 in Docker on `127.0.0.1:5434` (5432/5433 taken
locally); admin password in gitignored `.env`. Dump loaded in one transaction
with its `OWNER TO xiaolongli` lines stripped. 75/75 tables, row counts match
SQLite, 68 PKs + 87 FKs. No name collisions; near-collisions across DBs:
`card`/`cards`, `race`/`races` (good pooled-mode test cases). Re-verify with
`uv run python scripts/map_tables.py`.

---

## 1. The core design idea: one harness, pluggable strategies

Every milestone is a new *strategy* measured by the *same* harness on the *same*
frozen question set. Before/after comparisons fall out automatically; nothing
is hand-measured.

```python
class Strategy(Protocol):
    name: str
    def answer(self, question: Question) -> Prediction: ...

@dataclass
class Prediction:
    sql: str | None
    stages: list[StageTrace]   # one per stage: name, llm_calls, tokens_in,
                               # tokens_out, cached_tokens, latency_ms
```

| Milestone | Strategy added            | Compared against      |
|-----------|---------------------------|-----------------------|
| M1        | `full_schema`             | —                     |
| M3        | (linker only, no SQL)     | gold tables/columns   |
| M4        | `retrieve_select_generate`| `full_schema`         |
| M5        | `... + validate/repair`   | M4 run                |

`StageTrace` exists from M1 even though M1 has one stage. That makes M6
observability a reporting job, not a refactor.

## 2. What an eval run looks like

```
sample_50.json (frozen ids)
      │
      ▼
runner ── for each question ──► strategy.answer() ──► pred SQL
      │                                                  │
      │                         db.execute()  ◄──────────┘   (read-only role,
      │                              │                         audit-logged)
      ▼                              ▼
gold_results cache  ──── compare as sets ────► correct? 
      │
      ▼
runs/<timestamp>_<strategy>/
    config.json     git SHA, model, prompt hash, seed, price table, question ids
    results.jsonl   one row per question (below)
    summary.json    EX overall + by difficulty, total/mean tokens, p50/p95 latency, cost
```

`results.jsonl` row: `qid, db_id, difficulty, pred_sql, exec_error, correct,
rows_returned, truncated, tokens_in, tokens_out, cached_tokens, latency_ms, cost_usd`.

Cost is computed from recorded tokens × a price table in config, never
hardcoded, so old runs can be re-priced.

`compare.py runA runB` prints which questions got fixed and which broke.

## 3. Metrics

- **Execution accuracy (EX):** run gold and predicted SQL and compare the
  results as sets, the same way BIRD does. Timeouts and errors count as wrong.
  Gold results are computed once and cached.
- **Efficiency:** input/output/cached tokens, LLM calls, latency, $ per question.
- **Schema-linking recall (M3):** gold tables and columns are extracted from gold
  SQL with SQLGlot. Columns must be *qualified* against the schema first, or
  unqualified names and aliases get attributed to the wrong table. Report
  table recall@k and column recall@k for k ∈ {10, 20, 30, 50}.
  This needs no LLM, so measure it on **all 500** Mini-Dev questions, not 50.

**Statistical honesty.** With 50 questions, each one is worth 2 points. A
"+4 pt" gain is two questions. Always report the fixed/broken counts from
`compare.py`, not just the EX delta. Temperature 0 still isn't fully
deterministic, so re-run the baseline once to see how much it wobbles.

## 4. Security from day one

The rules sit in the database, and every query goes through a single `db.execute()`:

```sql
CREATE ROLE sqlagent_ro LOGIN;                      -- no superuser, no inheritance tricks
GRANT CONNECT ON DATABASE bird TO sqlagent_ro;
REVOKE TEMP ON DATABASE bird FROM PUBLIC;           -- no temp tables
GRANT USAGE ON SCHEMA <allowlisted> TO sqlagent_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA <allowlisted> TO sqlagent_ro;
ALTER ROLE sqlagent_ro SET default_transaction_read_only = on;
ALTER ROLE sqlagent_ro SET statement_timeout = '10s';
ALTER ROLE sqlagent_ro SET temp_file_limit = '100MB';
```

Why both GRANTs *and* `read_only`: a session can run `SET TRANSACTION READ
WRITE` and turn `read_only` off, so it isn't the real control. The real control is
privileges (SELECT only); `read_only` is a second layer. M1-S2 includes a test
proving writes fail even after that SET.

`db.execute()` is the only code path to the database. It writes the audit log
(timestamp, caller/strategy, question id, SQL, rows, duration, error), so no
caller can skip logging.

## 5. Threats to validity (keep these visible)

1. **Small schemas.** BIRD databases have few tables each. The thesis is about
   *large* schemas. → Pooled setup (D1).
2. **Evidence leakage.** BIRD hints name columns and values, which does the
   retriever's and value index's job for them. → D2.
3. **Prompt caching.** A static full-schema prefix can be cached, which cuts the
   baseline's input cost and latency. A cost win measured without caching is
   overstated. → D7.
4. **Strawman baseline.** A weak baseline makes anything look good. The
   baseline should be a reasonable full-schema prompt, using the same schema
   format the generator will use (D4, D5).
5. **Benchmark-specific help.** BIRD ships human-written column descriptions.
   Real databases usually don't. → M2 decision.

---

## 6. Roadmap

### M1 — Eval harness + full-schema baseline

| Session | Size | Task | Done when | Blocked by |
|---|---|---|---|---|
| S1 | 45m | Docker Postgres 16; load `BIRD_dev.sql`; map tables → `db_id`; check for name collisions | row counts match; mapping file committed | — |
| S2 | 45m | Roles SQL + `tests/test_security.py` | INSERT, CREATE, TEMP, `SET TRANSACTION READ WRITE`+INSERT all fail; `pg_sleep(20)` is killed | D6 |
| S3 | 45m | Frozen `eval/sample_50.json` (15 simple / 25 moderate / 10 challenging, fixed seed); run and cache gold results as `sqlagent_ro` | every gold query runs in under the timeout (replacements logged) | D1 |
| S4 | weekend | `db.execute` + audit log; `llm.py` wrapper recording tokens and latency; `full_schema` strategy; runner; EX | first `runs/` directory exists | D2, D3, D4, D5 |
| S5 | 45m | `summary` + `compare.py`; re-run baseline for variance; write `docs/RESULTS.md` | baseline numbers committed | D7 |

### M2 — Offline indexer
Descriptions, embeddings, FK graph, value index, table templating.
*Done when:* the index builds from scratch with one command, has a content
hash, and its offline LLM cost is recorded (offline cost is spread across
queries, not ignored). Descriptions and sampled values are stored as
untrusted text.

### M3 — Retriever (the go/no-go point)
Hybrid vector + BM25, no LLM.
*Done when:* recall@k is reported on all 500 questions, and table recall@30
meets the D8 threshold **chosen before looking at results**. If it fails,
iterate on M2/M3. Do not move on to M4.

### M4 — Selector
*Done when:* the M4 run is compared with the baseline on EX, tokens, latency
and $. Also report the selector's own recall: did cutting drop gold tables?

### M5 — Validator + escalation ladder
*Done when:* we report the % of bad SQL caught before execution, repair calls
per question, and the EX delta per rung of the ladder. Each rung must justify
its LLM calls.

### M6 — Observability, then FastAPI
Traces already exist (`StageTrace`), so this is reporting plus an API wrapper.

---

## Proposed layout (created as each session needs it, not upfront)

```
docker-compose.yml
sql/00_roles.sql
src/sqlagent/{config,db,llm}.py
src/sqlagent/eval/{dataset,metrics,runner,compare}.py
src/sqlagent/strategies/full_schema.py
eval/sample_50.json        # committed, frozen
data/                      # gitignored: BIRD dump, gold cache
runs/                      # gitignored except summary.json
tests/
```
