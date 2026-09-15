import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlagent import db
from sqlagent.schema import quote_identifier

MAX_DISTINCT = 1000
MAX_VALUE_CHARS = 100
TIMEOUT_MS = 60_000

TEXT_TYPES = ("text", "character varying", "character")
_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class ValueHit:
    table: str
    column: str
    value: str
    score: float


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _rows(execute, sql: str) -> list[tuple]:
    result = execute(sql, caller="index", question_id=None, timeout_ms=TIMEOUT_MS)
    if not result.ok:
        raise RuntimeError(f"value index query failed: {result.error_type}: {result.error}")
    return result.rows


def cardinality_estimates(execute) -> dict[tuple[str, str], float]:
    rows = _rows(
        execute,
        "SELECT s.tablename, s.attname, s.n_distinct, c.reltuples FROM pg_stats s "
        "JOIN pg_class c ON c.relname = s.tablename AND c.relnamespace = 'public'::regnamespace "
        "WHERE s.schemaname = 'public'",
    )
    return {(t, c): (n if n > 0 else -n * tuples) for t, c, n, tuples in rows}


def distinct_values(
    table: str, column: str, reserved: set[str], execute, max_distinct: int = MAX_DISTINCT
) -> list[str] | None:
    col, tbl = quote_identifier(column, reserved), quote_identifier(table, reserved)
    sql = f"SELECT DISTINCT {col} FROM {tbl} WHERE {col} IS NOT NULL LIMIT {int(max_distinct) + 1}"  # noqa: S608
    values = [r[0] for r in _rows(execute, sql)]
    return None if len(values) > max_distinct else values


class ValueIndex:
    def __init__(self, columns: dict[str, list[str]]):
        self.columns = {k: sorted(v) for k, v in sorted(columns.items())}
        self._postings: dict[str, list[tuple[str, str, frozenset[str]]]] = defaultdict(list)
        df: dict[str, int] = defaultdict(int)
        entries = 0
        for key, values in self.columns.items():
            for value in values:
                tokens = frozenset(tokenize(value))
                if not tokens:
                    continue
                entries += 1
                for t in tokens:
                    self._postings[t].append((key, value, tokens))
                    df[t] += 1
        self._idf = {t: math.log(1 + entries / n) for t, n in df.items()}

    @property
    def size(self) -> int:
        return sum(len(v) for v in self.columns.values())

    def lookup(self, text: str, limit: int = 20, min_score: float = 0.5) -> list[ValueHit]:
        query = set(tokenize(text))
        best: dict[tuple[str, str], float] = {}
        for token in query:
            for key, value, tokens in self._postings.get(token, ()):
                if (key, value) in best:
                    continue
                total = sum(self._idf[t] for t in tokens)
                matched = sum(self._idf[t] for t in tokens & query)
                best[(key, value)] = matched / total
        hits = [
            ValueHit(*key.split(".", 1), value, round(score, 4))
            for (key, value), score in best.items()
            if score >= min_score
        ]
        return sorted(hits, key=lambda h: (-h.score, h.table, h.column, h.value))[:limit]

    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.columns, sort_keys=True).encode()).hexdigest()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"columns": self.columns, "sha256": self.content_hash()}) + "\n")

    @classmethod
    def load(cls, path: Path) -> "ValueIndex":
        data = json.loads(path.read_text())
        index = cls(data["columns"])
        if index.content_hash() != data["sha256"]:
            raise ValueError(f"{path} content hash mismatch; rebuild the index")
        return index


def build_value_index(
    reserved: set[str],
    execute: Callable[..., db.QueryResult] = db.execute,
    max_distinct: int = MAX_DISTINCT,
) -> tuple[ValueIndex, dict]:
    placeholders = ", ".join(f"'{t}'" for t in TEXT_TYPES)
    columns = _rows(
        execute,
        "SELECT table_name, column_name FROM information_schema.columns "  # noqa: S608
        f"WHERE table_schema = 'public' AND data_type IN ({placeholders}) ORDER BY 1, 2",
    )
    estimates = cardinality_estimates(execute)
    indexed: dict[str, list[str]] = {}
    report = {
        "text_columns": len(columns),
        "no_statistics": 0,
        "skipped_high_cardinality": 0,
        "dropped_long_values": 0,
    }
    for table, column in columns:
        estimate = estimates.get((table, column))
        if estimate is None:
            report["no_statistics"] += 1
        elif estimate > 2 * max_distinct:
            report["skipped_high_cardinality"] += 1
            continue
        values = distinct_values(table, column, reserved, execute, max_distinct)
        if values is None:
            report["skipped_high_cardinality"] += 1
            continue
        kept = [v for v in values if len(v) <= MAX_VALUE_CHARS]
        report["dropped_long_values"] += len(values) - len(kept)
        if kept:
            indexed[f"{table}.{column}"] = kept
    index = ValueIndex(indexed)
    report.update({"indexed_columns": len(index.columns), "values": index.size, "max_distinct": max_distinct})
    return index, report
