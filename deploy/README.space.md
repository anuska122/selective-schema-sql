---
title: Selective Schema Text To SQL
emoji: 🗄️
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Selective-schema text-to-SQL API

Answers natural-language questions over 11 databases (75 tables, 798 columns)
by retrieving only the relevant tables instead of prompting with the whole
schema. Source and measured results: https://github.com/anuska122/selective-schema-sql

`POST /ask` requires the `x-api-token` header and is rate limited. All SQL runs
through a read-only Postgres role with a statement timeout and a row cap.


## Required secrets

Set `GROQ_API_KEY` and a strong `SQLAGENT_API_TOKEN` in the hosting platform's
secret settings. The container refuses to start if either is absent. The web
server must use the matching server-only `API_TOKEN` and point `BACKEND_URL` here.

## Probes and quotas

`GET /health` is liveness; `GET /ready` validates local pipeline/index/database
readiness without calling the model provider. It cannot validate the model key.
The Docker health check uses `/ready`.

SQLite quotas default to `/home/user/quota/limits.sqlite3`. Persist or bind that
path to platform storage to preserve counts across container replacement. Local
workers using the same file share atomic daily and per-client clock-hour budgets.
Separate hosts require a central quota service. Do not share SQLite over NFS.

Defaults: `SQLAGENT_DAILY_QUESTIONS=100`, `SQLAGENT_HOURLY_QUESTIONS=5`.
`SQLAGENT_PAUSED=1` stops new questions. A successful token check reserves quota
before generation, so failed or cancelled requests can count toward the budget.
Forwarded client identities should come only from the trusted web server.

## Verification boundary

The full 498-question reference/harness check passes with an explicit 50,000-row
evaluation cap. Model benchmarks and a successful live answer remain blocked by
the currently rejected provider key; this does not change historical model scores.
See the source README for resumable runs and exact evaluation commands.
