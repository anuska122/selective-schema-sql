# Project status

The index, retrieval/selection, SQL generation, repair ladder, API, web UI and
benchmark tooling are implemented. README.md contains setup and usage commands.

## Completed maintenance

- Strict existing-index checks: vector count, IDs, documents, metadata, database
  mapping and available manifest hashes/model must agree.
- Quota/provider failures abort evaluation rather than becoming accuracy failures.
- Invalid final SQL is not executed; HTTP errors hide internal diagnostics.
- Request IDs correlate API answers, validation and execution audit records.
- Separate liveness and readiness, with Docker probing readiness.
- Atomic SQLite quota reservations shared across workers on one host, plus explicit
  web proxy trust configuration and token enforcement in the public Docker entrypoint.
- Mobile navigation, saved-database restoration, database-list recovery and cancellation.
- Explicit set/multiset/ordered evaluation modes; reject mixed-mode or mixed-cap
  reports and resumes. New runs fingerprint question contents.
- Full 498-question gold cache and 100% gold-oracle execution check using an explicit
  50,000-row evaluation cap. No benchmark questions were removed.
- Heuristic error-analysis CLI and full retrieval traces for future diagnosis.
- README, environment example, deployment instructions and versionable planning docs.

## External verification limits

- Groq rejects the current configured key with HTTP 401. Model benchmarks remain
  blocked. The full-schema and selective
  runs are incomplete with zero answered questions, not 0% accuracy.
- After repairing the key, resume the two run directories recorded in README.md,
  repeat the paired comparison, and verify a successful authenticated live answer.
- The computer/browser host is unavailable, so visual mobile verification remains
  unperformed. Automated navigation and recovery interaction tests pass.
- Local verification does not establish remote delivery or CI status; verify those
  separately for the delivered commit.

## Validation

```sh
scripts/apply_roles.sh
REQUIRE_DB=1 uv run pytest
uv run ruff check
uv run ruff format --check
cd web
npm test
npm run lint
npm run typecheck
npm run build
```

## Latest local verification (2026-11-16)

- 380 Python tests pass with REQUIRE_DB=1; 98.77% coverage.
- 54 web tests pass; Python lint/format and web lint/typecheck/build pass.
- Full reference cache: 498 questions, no failures, explicit 50,000-row cap.
- Full gold-oracle evaluation: 498/498 correct; no model calls.
- Docker image builds; local readiness returns 200, missing-token requests return
  401 and authenticated requests over quota return 429.
- Persisted quota is retained after container restart and replacement using the same volume.
- Browser host remains unavailable; model credentials remain rejected. No claim
  of visual verification, fresh model accuracy or a successful live answer is made.
