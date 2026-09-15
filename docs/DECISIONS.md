# Decisions

Format: context → options → recommendation → **choice (yours)** → why.
Status: `OPEN` · `PROPOSED` (default unless you object) · `DECIDED`.

---

## D0 · Benchmark data — PROPOSED
Use **BIRD Mini-Dev, PostgreSQL version** (`mini_dev_postgresql.json`, dump
`BIRD_dev.sql`; 500 SELECT-only questions, 30/50/20 simple/moderate/challenging).
Why: native Postgres gold SQL. The full dev set is SQLite only, and converting
its gold SQL ourselves could put errors into the answers we grade against.
M1 uses a frozen 50-question stratified sample with a fixed seed; M3 recall uses all 500.

## D1 · Database layout — OPEN · blocks M1-S3
Mini-Dev loads all 11 DBs into **one** Postgres database.
- **Pooled:** each question sees all ~75 tables. This is the setup that tests the thesis, and it's free.
- **Standard:** each question sees only its own `db_id`'s tables. Comparable to
  published numbers; needs the table→db_id mapping (built in S1 anyway).
- **Both:** about twice the baseline LLM calls.
Recommendation: **Both** for the M1 baseline, pooled as the main setup after that.
Choice: —

## D2 · BIRD evidence hints — OPEN · blocks M1-S4
- **Without:** tests whether descriptions and the value index do their job. EX will look lower than the leaderboard.
- **With:** comparable to published numbers; hides retriever and value-index weaknesses.
Recommendation: **without**.
Choice: —

## D3 · LLM provider / models — OPEN · blocks M1-S4
Baseline must use the same model as the future generator. Also decide the
cheap selector model now so the price table is ready. Depends on what you have
credits or access for.
Choice: —

## D4 · Schema format in prompts — OPEN · blocks M1-S4
Must be identical for baseline and generator, or the comparison is confounded.
- **CREATE TABLE DDL with FKs:** familiar to models, more tokens.
- **Compact** `table(col type, ...)` + FK lines: fewer tokens, less standard.
Recommendation: **DDL** for the baseline. If compact wins later, it's a
separate before/after, not something folded into the retrieval result.
Choice: —

## D5 · Baseline strength: sample rows? — OPEN · blocks M1-S4
- **No sample rows:** cheaper baseline, but weaker on value-matching questions.
- **3 sample rows per table:** a stronger, fairer baseline, with more tokens in pooled mode.
Recommendation: **3 rows**. Don't strawman the thing you're trying to beat.
Choice: —

## D6 · Row limit enforcement — OPEN · blocks M1-S2
Postgres has **no built-in per-role row limit**. Real DB-level controls:
`statement_timeout`, `temp_file_limit`, `work_mem`. Row cap options:
- **Server-side cursor + fetchmany(N)** in `db.execute` (app layer, but a single
  code path). Doesn't change the SQL, so EX stays correct; flags `truncated`.
- **Wrap as `SELECT * FROM (q) LIMIT N`**. Changes query semantics and can
  break EX comparison with gold.
Recommendation: **cursor + fetchmany**, with the DB-level resource limits above
as the enforcement Postgres can actually provide. Update the security wording in the project brief.
Choice: —

## D7 · Cost accounting with prompt caching — OPEN · blocks M1-S5
- **Report baseline cost both uncached and cached:** honest, and the cost claim survives scrutiny.
- **Uncached only:** simpler, overstates the win.
Recommendation: **both**.
Choice: —

## D8 · M3 go/no-go recall threshold — OPEN · decide before M3 results
Pre-register the table recall@30 needed to proceed to M4 (e.g. ≥ 95%).
Choose it before seeing numbers so it can't be tuned to pass.
Choice: —
