import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlagent import db

SAMPLE_ROWS = 3
MAX_VALUE_CHARS = 100

_SIMPLE_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")


@dataclass
class Table:
    name: str
    columns: list[tuple[str, str]] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    sample_header: list[str] = field(default_factory=list)
    sample_rows: list[tuple] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)


def _query(execute: Callable[..., db.QueryResult], sql: str) -> list[tuple]:
    result = execute(sql, caller="schema", question_id=None)
    if not result.ok:
        raise RuntimeError(f"schema introspection failed: {result.error_type}: {result.error}")
    return result.rows


def quote_identifier(name: str, reserved: set[str]) -> str:
    if _SIMPLE_IDENTIFIER.fullmatch(name) and name not in reserved:
        return name
    return '"' + name.replace('"', '""') + '"'


def sanitize_value(value) -> str:
    text = "NULL" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("*/", "* /").replace("</", "< /")
    if len(text) > MAX_VALUE_CHARS:
        text = text[: MAX_VALUE_CHARS - 1] + "…"
    return text


def load_tables(
    names: list[str], execute: Callable[..., db.QueryResult] = db.execute, sample_rows: int = SAMPLE_ROWS
) -> tuple[list[Table], set[str]]:
    reserved = {
        r[0] for r in _query(execute, "SELECT word FROM pg_get_keywords() WHERE catcode IN ('R', 'T')")
    }
    tables = {n: Table(n) for n in names}
    for table, column, data_type in _query(
        execute,
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position",
    ):
        if table in tables:
            tables[table].columns.append((column, data_type))
    for table, _, definition in _query(
        execute,
        "SELECT conrelid::regclass::text, contype, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE connamespace = 'public'::regnamespace AND contype IN ('p', 'f') ORDER BY 1, 2 DESC, conname",
    ):
        name = table.strip('"')
        if name in tables:
            tables[name].constraints.append(definition)
    for table, column in _query(
        execute,
        "SELECT c.conrelid::regclass::text, a.attname FROM pg_constraint c "
        "CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) "
        "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum "
        "WHERE c.contype = 'p' AND c.connamespace = 'public'::regnamespace ORDER BY 1, k.ord",
    ):
        name = table.strip('"')
        if name in tables:
            tables[name].primary_key.append(column)
    if sample_rows:
        for t in tables.values():
            sql = f"SELECT * FROM {quote_identifier(t.name, reserved)} ORDER BY {_sample_order(t, reserved)} "  # noqa: S608
            sql += f"LIMIT {int(sample_rows)}"
            result = execute(sql, caller="schema", question_id=None)
            if not result.ok:
                raise RuntimeError(f"sampling {t.name} failed: {result.error}")
            t.sample_header, t.sample_rows = result.columns, result.rows
    return [tables[n] for n in names], reserved


def _sample_order(table: Table, reserved: set[str]) -> str:
    if table.primary_key:
        return ", ".join(quote_identifier(c, reserved) for c in table.primary_key)
    return ", ".join(str(i) for i in range(1, len(table.columns) + 1))


def render_table(table: Table, reserved: set[str]) -> str:
    lines = [f"  {quote_identifier(c, reserved)} {data_type}" for c, data_type in table.columns]
    lines += [f"  {c}" for c in table.constraints]
    ddl = f"CREATE TABLE {quote_identifier(table.name, reserved)} (\n" + ",\n".join(lines) + "\n);"
    if not table.sample_rows:
        return ddl
    rows = "\n".join(" | ".join(sanitize_value(v) for v in row) for row in table.sample_rows)
    header = " | ".join(table.sample_header)
    return f"{ddl}\n/* {len(table.sample_rows)} example rows from {table.name}:\n{header}\n{rows}\n*/"


def render_schema(tables: list[Table], reserved: set[str]) -> str:
    return "\n\n".join(render_table(t, reserved) for t in tables)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
