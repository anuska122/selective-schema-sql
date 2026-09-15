import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from sqlagent import config, db
from sqlagent.eval.dataset import Question

GOLD_CACHE = config.ROOT / "data" / "gold" / "sample_50.json"


@dataclass(frozen=True)
class GoldResult:
    question_id: int
    sql_sha256: str
    columns: list[str]
    rows: list[tuple]
    duration_ms: float


def sql_hash(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()


def encode_value(v):
    if isinstance(v, Decimal):
        return {"$decimal": str(v)}
    if isinstance(v, datetime):
        return {"$datetime": v.isoformat()}
    if isinstance(v, date):
        return {"$date": v.isoformat()}
    if isinstance(v, time):
        return {"$time": v.isoformat()}
    if isinstance(v, timedelta):
        return {"$timedelta": v.total_seconds()}
    if isinstance(v, bytes | memoryview):
        return {"$bytes": bytes(v).hex()}
    return v


_DECODERS = {
    "$decimal": Decimal,
    "$datetime": datetime.fromisoformat,
    "$date": date.fromisoformat,
    "$time": time.fromisoformat,
    "$timedelta": lambda s: timedelta(seconds=s),
    "$bytes": bytes.fromhex,
}


def decode_value(v):
    if isinstance(v, dict) and len(v) == 1:
        ((tag, payload),) = v.items()
        return _DECODERS[tag](payload)
    return v


def compute_gold(
    questions: list[Question], execute: Callable[..., db.QueryResult] = db.execute
) -> tuple[dict[int, GoldResult], list[str]]:
    results: dict[int, GoldResult] = {}
    failures: list[str] = []
    for q in questions:
        r = execute(q.gold_sql, caller="gold", question_id=q.question_id)
        if not r.ok:
            failures.append(f"{q.question_id}: {r.error_type}: {r.error}")
        elif r.truncated:
            failures.append(f"{q.question_id}: gold result exceeds the row cap")
        else:
            results[q.question_id] = GoldResult(
                q.question_id, sql_hash(q.gold_sql), r.columns, r.rows, r.duration_ms
            )
    return results, failures


def save_gold(results: dict[int, GoldResult], path: Path = GOLD_CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        str(qid): {
            "sql_sha256": g.sql_sha256,
            "columns": g.columns,
            "rows": [[encode_value(v) for v in row] for row in g.rows],
            "duration_ms": g.duration_ms,
        }
        for qid, g in sorted(results.items())
    }
    path.write_text(json.dumps(payload, indent=1) + "\n")


def load_gold(questions: list[Question], path: Path = GOLD_CACHE) -> dict[int, GoldResult]:
    payload = json.loads(path.read_text())
    results = {}
    for q in questions:
        entry = payload.get(str(q.question_id))
        if entry is None:
            raise KeyError(f"no cached gold result for question {q.question_id}; rebuild the cache")
        if entry["sql_sha256"] != sql_hash(q.gold_sql):
            raise ValueError(f"gold SQL for question {q.question_id} changed; rebuild the cache")
        results[q.question_id] = GoldResult(
            q.question_id,
            entry["sql_sha256"],
            entry["columns"],
            [tuple(decode_value(v) for v in row) for row in entry["rows"]],
            entry["duration_ms"],
        )
    return results
