# Implementation decisions

## Explicit orchestration

The request pipeline uses ordinary Python orchestration. Retrieval, graph traversal,
and validation do not call a model. A normal request uses selector and generator
calls; one repair and one widened regeneration are available on validation failure.
Quota exhaustion aborts immediately. Invalid final SQL is not passed to execution.

## Error boundary

Internal services retain diagnostic errors for evaluation and logging. The HTTP
API replaces execution errors with recovery copy and removes validation error text
from response details. SQL, selected tables, lineage, and stage timings remain visible. A request ID connects the response to SQL
validation and execution audit records; raw question text is not added to audit logs.

## Liveness and readiness

`/health` reports process liveness. `/ready` initializes the cached service and
checks database-role safety on each probe. Index initialization rejects missing,
empty, stale or inconsistent vector artifacts. A failed initialization can be retried.
Readiness returns generic 503 errors and makes no paid model calls. Production
routing must use `/ready`; a successful liveness probe is insufficient.

## Evaluation comparison modes

Historical results used set equality, ignoring duplicates and row order. Keep
that mode explicitly available for reproducibility and preserve the historical
scores. New runs default to multiset equality, retaining duplicate counts while
ignoring order. Ordered equality is available for order-sensitive evaluations.
These modes are custom metrics; no official BIRD evaluator equivalence is claimed.
Record the mode in configuration and summaries, reject mixed-mode resumes and
comparisons, and keep the frozen sample unchanged. Full-dataset evaluation uses
a separate gold cache and stops if reference results cannot be computed safely.

## Evaluation row policy

Use an explicit 50,000-row cap for full-dataset gold and prediction execution.
This covers reference IDs 340 (25,061 rows), 346 (29,936) and 397 (11,446)
without changing the public API's 100-row output limit or the normal 10,000-row
execution default. The cap is recorded in gold-cache metadata and run configuration;
cache loading, resume and comparisons reject inconsistent limits. The CLI caps
this opt-in setting at one million rows. SQL read-only and timeout protections apply.

Authentication, network and exhausted-retry provider failures abort runs as
incomplete; they must not become incorrect-answer counts. The gold-oracle check
only proves reference execution/harness consistency, not model accuracy.

## Demo deployment boundary

The API shared token protects model-backed requests when configured. It is not
per-user authentication. Database contents are public BIRD data, execution uses a
read-only role, and the Docker entrypoint requires both token and model-key configuration.
SQLite-backed quotas serialize reservations across workers sharing a local file.
Persist that file on a local Docker volume across container replacement. Different
hosts need a central quota service; do not place SQLite on a network filesystem.
Forwarded client identities are accepted only through the token-protected API,
and the web trusts proxy IP headers only when explicitly configured. Private data
still requires a separate per-user access design.

## Cancellation

Cancellation aborts the browser fetch and web proxy wait. It does not promise
termination of a model call or SQL operation already running in the synchronous
API. The UI explains this, and reserved quota is not refunded on cancellation.
