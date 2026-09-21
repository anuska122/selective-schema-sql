import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import sqlglot
from psycopg import sql
from sqlglot import exp
from sqlglot.errors import ParseError

from sqlagent import config

MAX_ROWS = 10_000
STATEMENT_TIMEOUT_MS = 10_000

_FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Command,
    exp.Copy,
    exp.Set,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
    exp.Grant,
)


class RejectedQuery(ValueError):
    pass


@dataclass(frozen=True)
class QueryResult:
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    truncated: bool = False
    duration_ms: float = 0.0
    error: str | None = None
    error_type: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def validate_select(query: str) -> str:
    try:
        statements = [s for s in sqlglot.parse(query, read="postgres") if s is not None]
    except ParseError as e:
        raise RejectedQuery(f"unparseable SQL: {e}") from e
    if len(statements) != 1:
        raise RejectedQuery(f"expected exactly one statement, got {len(statements)}")
    (tree,) = statements
    if not isinstance(tree, exp.Query):
        raise RejectedQuery(f"only SELECT queries are allowed, got {type(tree).__name__}")
    forbidden = next(tree.find_all(*_FORBIDDEN_NODES), None)
    if forbidden is not None:
        raise RejectedQuery(f"forbidden operation: {type(forbidden).__name__}")
    for node in tree.find_all(exp.Select):
        if node.args.get("into"):
            raise RejectedQuery("SELECT INTO is not allowed")
        if node.args.get("locks"):
            raise RejectedQuery("row locking clauses are not allowed")
    return query.strip().rstrip(";").strip()


def execute(
    query: str,
    *,
    caller: str,
    question_id: int | str | None = None,
    max_rows: int = MAX_ROWS,
    timeout_ms: int = STATEMENT_TIMEOUT_MS,
    audit_path: Path | None = None,
) -> QueryResult:
    return _run(
        query, validate_select, caller, question_id, max_rows, timeout_ms, audit_path, server_cursor=True
    )


def explain(
    query: str,
    *,
    caller: str,
    question_id: int | str | None = None,
    timeout_ms: int = STATEMENT_TIMEOUT_MS,
    audit_path: Path | None = None,
) -> QueryResult:
    def as_explain(sql: str) -> str:
        return f"EXPLAIN {validate_select(sql)}"

    return _run(query, as_explain, caller, question_id, MAX_ROWS, timeout_ms, audit_path, server_cursor=False)


def _run(
    query: str,
    prepare,
    caller: str,
    question_id: int | str | None,
    max_rows: int,
    timeout_ms: int,
    audit_path: Path | None,
    *,
    server_cursor: bool,
) -> QueryResult:
    start = time.perf_counter()
    result: QueryResult
    try:
        checked = prepare(query)
        with psycopg.connect(config.ro_dsn(), connect_timeout=5) as conn, conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute(sql.SQL("SET LOCAL statement_timeout = {}").format(sql.Literal(timeout_ms)))
            cursor = conn.cursor(name="sqlagent_query") if server_cursor else conn.cursor()
            with cursor as cur:
                cur.execute(checked)
                rows = cur.fetchmany(max_rows + 1)
                columns = [c.name for c in cur.description or []]
        result = QueryResult(
            columns=columns,
            rows=rows[:max_rows],
            truncated=len(rows) > max_rows,
            duration_ms=_elapsed_ms(start),
        )
    except RejectedQuery as e:
        result = QueryResult(duration_ms=_elapsed_ms(start), error=str(e), error_type="rejected")
    except psycopg.errors.QueryCanceled as e:
        result = QueryResult(duration_ms=_elapsed_ms(start), error=_first_line(e), error_type="timeout")
    except psycopg.Error as e:
        result = QueryResult(duration_ms=_elapsed_ms(start), error=_first_line(e), error_type="db_error")
    _audit(audit_path or config.ROOT / "audit" / "queries.jsonl", caller, question_id, query, result)
    return result


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 2)


def _first_line(e: Exception) -> str:
    return str(e).splitlines()[0] if str(e) else type(e).__name__


def _audit(path: Path, caller: str, question_id, query: str, result: QueryResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "caller": caller,
        "question_id": question_id,
        "sql": query,
        "rows": len(result.rows),
        "truncated": result.truncated,
        "duration_ms": result.duration_ms,
        "error_type": result.error_type,
        "error": result.error,
    }
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")
