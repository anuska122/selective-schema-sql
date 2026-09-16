import hashlib
import json
from collections import defaultdict, deque
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlagent import db

FK_QUERY = """
SELECT c.conname, c.conrelid::regclass::text, c.confrelid::regclass::text, k.ord, a.attname, af.attname
FROM pg_constraint c
CROSS JOIN LATERAL unnest(c.conkey, c.confkey) WITH ORDINALITY AS k(src, dst, ord)
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.src
JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = k.dst
WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace
ORDER BY 1, 4
"""


@dataclass(frozen=True)
class ForeignKey:
    name: str
    table: str
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]
    source: str = "declared"
    rule: str | None = None
    coverage: float | None = None

    def join_condition(self) -> str:
        return " AND ".join(
            f"{self.table}.{c} = {self.ref_table}.{r}"
            for c, r in zip(self.columns, self.ref_columns, strict=True)
        )


def load_foreign_keys(execute: Callable[..., db.QueryResult] = db.execute) -> list[ForeignKey]:
    result = execute(FK_QUERY, caller="index", question_id=None)
    if not result.ok:
        raise RuntimeError(f"foreign key introspection failed: {result.error_type}: {result.error}")
    grouped: dict[str, dict] = {}
    for name, table, ref_table, _, column, ref_column in result.rows:
        fk = grouped.setdefault(
            name, {"table": table.strip('"'), "ref_table": ref_table.strip('"'), "cols": [], "refs": []}
        )
        fk["cols"].append(column)
        fk["refs"].append(ref_column)
    return [
        ForeignKey(name, g["table"], tuple(g["cols"]), g["ref_table"], tuple(g["refs"]))
        for name, g in sorted(grouped.items())
    ]


class FKGraph:
    def __init__(self, foreign_keys: Iterable[ForeignKey], tables: Iterable[str] = ()):
        self.foreign_keys = sorted(foreign_keys, key=lambda fk: fk.name)
        self._edges: dict[frozenset[str], list[ForeignKey]] = defaultdict(list)
        self._adjacent: dict[str, set[str]] = defaultdict(set)
        for t in tables:
            self._adjacent[t]
        for fk in self.foreign_keys:
            self._adjacent[fk.table]
            self._adjacent[fk.ref_table]
            if fk.table != fk.ref_table:
                self._adjacent[fk.table].add(fk.ref_table)
                self._adjacent[fk.ref_table].add(fk.table)
            self._edges[frozenset((fk.table, fk.ref_table))].append(fk)

    @property
    def tables(self) -> list[str]:
        return sorted(self._adjacent)

    def neighbors(self, table: str) -> list[str]:
        return sorted(self._adjacent.get(table, ()))

    def edges_between(self, a: str, b: str) -> list[ForeignKey]:
        return list(self._edges.get(frozenset((a, b)), []))

    def join_path(self, start: str, goal: str) -> list[str] | None:
        return self._shortest_path({start}, {goal})

    def connect(self, tables: Iterable[str]) -> tuple[list[str], list[tuple[str, str]]] | None:
        terminals = sorted(set(tables))
        if not terminals or any(t not in self._adjacent for t in terminals):
            return None
        connected = {terminals[0]}
        joins: list[tuple[str, str]] = []
        remaining = set(terminals[1:]) - connected
        while remaining:
            path = self._shortest_path(connected, remaining)
            if path is None:
                return None
            for a, b in zip(path, path[1:], strict=False):
                joins.append((a, b))
                connected.add(b)
            remaining -= connected
        return sorted(connected), joins

    def components(self, tables: Iterable[str]) -> list[list[str]]:
        scope = set(tables)
        seen: set[str] = set()
        groups = []
        for start in sorted(scope):
            if start in seen:
                continue
            group, queue = [], deque([start])
            seen.add(start)
            while queue:
                t = queue.popleft()
                group.append(t)
                for n in self.neighbors(t):
                    if n in scope and n not in seen:
                        seen.add(n)
                        queue.append(n)
            groups.append(sorted(group))
        return groups

    def _shortest_path(self, sources: set[str], goals: set[str]) -> list[str] | None:
        if sources & goals:
            return [min(sources & goals)]
        previous: dict[str, str | None] = {s: None for s in sorted(sources)}
        queue = deque(sorted(sources))
        while queue:
            t = queue.popleft()
            for n in self.neighbors(t):
                if n in previous:
                    continue
                previous[n] = t
                if n in goals:
                    path = [n]
                    while previous[path[-1]] is not None:
                        path.append(previous[path[-1]])
                    return path[::-1]
                queue.append(n)
        return None

    def to_dict(self) -> dict:
        return {"tables": self.tables, "foreign_keys": [asdict(fk) for fk in self.foreign_keys]}

    @classmethod
    def from_dict(cls, data: dict) -> "FKGraph":
        fks = [
            ForeignKey(
                **{**f, "columns": tuple(f["columns"]), "ref_columns": tuple(f["ref_columns"])},
            )
            for f in data["foreign_keys"]
        ]
        return cls(fks, data["tables"])

    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({**self.to_dict(), "sha256": self.content_hash()}, indent=1) + "\n")

    @classmethod
    def load(cls, path: Path) -> "FKGraph":
        data = json.loads(path.read_text())
        graph = cls.from_dict(data)
        if graph.content_hash() != data["sha256"]:
            raise ValueError(f"{path} content hash mismatch; rebuild the index")
        return graph
