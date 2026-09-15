from collections.abc import Callable, Iterable
from dataclasses import dataclass

from sqlagent import db
from sqlagent.index.fk_graph import ForeignKey
from sqlagent.schema import quote_identifier

MIN_COVERAGE = 0.95
TIMEOUT_MS = 60_000

GENERIC_NAMES = {
    "id",
    "name",
    "date",
    "type",
    "code",
    "description",
    "status",
    "year",
    "value",
    "title",
    "text",
    "url",
    "number",
    "label",
}
_FAMILIES = [
    {"smallint", "integer", "bigint"},
    {"text", "character varying", "character"},
]


@dataclass(frozen=True)
class Column:
    table: str
    name: str
    data_type: str


@dataclass(frozen=True)
class Candidate:
    child: Column
    parent: Column
    rule: str


def type_family(data_type: str) -> str:
    for family in _FAMILIES:
        if data_type in family:
            return min(family)
    return data_type


def singular(name: str) -> str:
    return name[:-1] if name.endswith("s") and not name.endswith("ss") else name


def match_rule(child: Column, parent: Column) -> str | None:
    if type_family(child.data_type) != type_family(parent.data_type):
        return None
    if child.name == parent.name and child.name not in GENERIC_NAMES:
        return "same_name"
    prefixes = {parent.table, singular(parent.table)}
    if child.name in {f"{p}{sep}{parent.name}" for p in prefixes for sep in ("", "_")}:
        return "named_after_table"
    return None


def candidates(
    columns: Iterable[Column], scopes: Iterable[Iterable[str]], declared: Iterable[ForeignKey]
) -> list[Candidate]:
    by_table: dict[str, list[Column]] = {}
    for c in columns:
        by_table.setdefault(c.table, []).append(c)
    known = set()
    for fk in declared:
        for col, ref in zip(fk.columns, fk.ref_columns, strict=True):
            known.add(frozenset(((fk.table, col), (fk.ref_table, ref))))
    found = []
    for scope in scopes:
        tables = sorted(t for t in scope if t in by_table)
        for child_table in tables:
            for parent_table in tables:
                if child_table == parent_table:
                    continue
                for child in by_table[child_table]:
                    for parent in by_table[parent_table]:
                        rule = match_rule(child, parent)
                        pair = frozenset(((child.table, child.name), (parent.table, parent.name)))
                        if rule and pair not in known:
                            found.append(Candidate(child, parent, rule))
    return found


def _scalar_row(execute, sql: str) -> tuple:
    result = execute(sql, caller="index", question_id=None, timeout_ms=TIMEOUT_MS)
    if not result.ok:
        raise RuntimeError(f"key inference query failed: {result.error_type}: {result.error}")
    return result.rows[0]


def is_unique(column: Column, reserved: set[str], execute) -> bool:
    col, table = quote_identifier(column.name, reserved), quote_identifier(column.table, reserved)
    non_null, distinct = _scalar_row(execute, f"SELECT count({col}), count(DISTINCT {col}) FROM {table}")  # noqa: S608
    return non_null > 0 and non_null == distinct


def coverage(child: Column, parent: Column, reserved: set[str], execute) -> float | None:
    def q(name: str) -> str:
        return quote_identifier(name, reserved)

    sql = (
        f"SELECT count(*), count(p.v) FROM (SELECT DISTINCT {q(child.name)} AS v FROM {q(child.table)} "  # noqa: S608
        f"WHERE {q(child.name)} IS NOT NULL) d "
        f"LEFT JOIN (SELECT DISTINCT {q(parent.name)} AS v FROM {q(parent.table)}) p ON p.v = d.v"
    )
    total, matched = _scalar_row(execute, sql)
    return matched / total if total else None


def infer_foreign_keys(
    columns: list[Column],
    scopes: list[list[str]],
    declared: list[ForeignKey],
    reserved: set[str],
    execute: Callable[..., db.QueryResult] = db.execute,
    min_coverage: float = MIN_COVERAGE,
) -> tuple[list[ForeignKey], list[dict]]:
    report = []
    accepted: dict[frozenset, ForeignKey] = {}
    unique_cache: dict[Column, bool] = {}
    for cand in candidates(columns, scopes, declared):
        if cand.parent not in unique_cache:
            unique_cache[cand.parent] = is_unique(cand.parent, reserved, execute)
        row = {
            "child": f"{cand.child.table}.{cand.child.name}",
            "parent": f"{cand.parent.table}.{cand.parent.name}",
            "rule": cand.rule,
            "parent_unique": unique_cache[cand.parent],
            "coverage": None,
            "accepted": False,
        }
        if unique_cache[cand.parent]:
            row["coverage"] = coverage(cand.child, cand.parent, reserved, execute)
            if row["coverage"] is not None and row["coverage"] >= min_coverage:
                fk = ForeignKey(
                    name=f"inferred:{row['child']}->{row['parent']}",
                    table=cand.child.table,
                    columns=(cand.child.name,),
                    ref_table=cand.parent.table,
                    ref_columns=(cand.parent.name,),
                    source="inferred",
                    rule=cand.rule,
                    coverage=round(row["coverage"], 4),
                )
                pair = frozenset(((fk.table, fk.columns), (fk.ref_table, fk.ref_columns)))
                current = accepted.get(pair)
                if current is None or fk.coverage > current.coverage:
                    accepted[pair] = fk
        report.append(row)
    kept = {fk.name for fk in accepted.values()}
    for row in report:
        row["accepted"] = f"inferred:{row['child']}->{row['parent']}" in kept
    return sorted(accepted.values(), key=lambda fk: fk.name), report
