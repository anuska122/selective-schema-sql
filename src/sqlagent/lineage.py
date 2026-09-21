from sqlglot.errors import ParseError

from sqlagent.index.fk_graph import FKGraph
from sqlagent.validation.validator import referenced_names


def query_lineage(sql: str | None, tables: list[str], graph: FKGraph) -> dict:
    joins = []
    for i, a in enumerate(tables):
        for b in tables[i + 1 :]:
            for fk in graph.edges_between(a, b):
                joins.append(
                    {
                        "from": fk.table,
                        "from_columns": list(fk.columns),
                        "to": fk.ref_table,
                        "to_columns": list(fk.ref_columns),
                        "inferred": fk.source == "inferred",
                    }
                )
    columns: dict[str, list[str]] = {}
    if sql:
        try:
            used_tables, used_columns = referenced_names(sql)
        except (ParseError, ValueError):
            used_tables, used_columns = set(), {}
        for table in tables:
            if table in used_tables:
                columns[table] = sorted(used_columns.get(table, set()))
        unqualified = used_columns.get(None, set())
        if unqualified and len(columns) == 1:
            only = next(iter(columns))
            columns[only] = sorted(set(columns[only]) | unqualified)
    return {"joins": joins, "columns": columns}
