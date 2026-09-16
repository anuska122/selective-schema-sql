from collections.abc import Callable
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from sqlagent import db


@dataclass(frozen=True)
class Validation:
    ok: bool
    stage: str
    errors: list[str] = field(default_factory=list)

    @property
    def message(self) -> str:
        return "; ".join(self.errors)


def derived_names(tree: exp.Expression) -> set[str]:
    names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    names |= {sub.alias_or_name.lower() for sub in tree.find_all(exp.Subquery) if sub.alias_or_name}
    names |= {alias.alias_or_name.lower() for alias in tree.find_all(exp.Alias) if alias.alias_or_name}
    return names


def referenced_names(sql: str) -> tuple[set[str], dict[str | None, set[str]]]:
    tree = sqlglot.parse_one(sql, read="postgres")
    derived = derived_names(tree)
    aliases: dict[str, str] = {}
    tables: set[str] = set()
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if name in derived:
            continue
        tables.add(name)
        aliases[(table.alias or name).lower()] = name
    columns: dict[str | None, set[str]] = {}
    for column in tree.find_all(exp.Column):
        if column.name.lower() in derived:
            continue
        owner_key = column.table.lower()
        if owner_key and owner_key not in aliases:
            continue
        owner = aliases.get(owner_key) if owner_key else None
        columns.setdefault(owner, set()).add(column.name.lower())
    return tables, columns


def check_names(sql: str, catalog: dict[str, set[str]]) -> list[str]:
    tables, columns = referenced_names(sql)
    errors = [f"unknown table: {t}" for t in sorted(tables - catalog.keys())]
    known = tables & catalog.keys()
    for owner, names in sorted(columns.items(), key=lambda kv: kv[0] or ""):
        scope = catalog.get(owner, set()) if owner else {c for t in known for c in catalog[t]}
        if owner and owner not in catalog:
            continue
        for name in sorted(names - scope):
            errors.append(f"unknown column: {owner + '.' if owner else ''}{name}")
    return errors


class Validator:
    def __init__(self, catalog: dict[str, set[str]], explain: Callable[..., db.QueryResult] = db.explain):
        self.catalog = {t.lower(): {c.lower() for c in cols} for t, cols in catalog.items()}
        self.explain = explain

    def validate(self, sql: str | None, *, question_id: int | str | None = None) -> Validation:
        if not sql:
            return Validation(False, "parse", ["no SQL produced"])
        try:
            db.validate_select(sql)
        except db.RejectedQuery as e:
            return Validation(False, "parse", [str(e)])

        errors = check_names(sql, self.catalog)
        if errors:
            return Validation(False, "names", errors)

        plan = self.explain(sql, caller="validator", question_id=question_id)
        if not plan.ok:
            return Validation(False, "explain", [f"{plan.error_type}: {plan.error}"])
        return Validation(True, "ok")
