from collections import defaultdict
from dataclasses import dataclass, field

from sqlagent.index.embeddings import SchemaDocument, SchemaIndex
from sqlagent.index.values import ValueIndex
from sqlagent.retrieval.bm25 import BM25

RRF_K = 60
CANDIDATE_DEPTH = 100


@dataclass(frozen=True)
class TableCandidate:
    table: str
    db_id: str
    score: float
    columns: list[str] = field(default_factory=list)
    values: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


def _table_of(document_id: str) -> str:
    body = document_id.split(":", 1)[1]
    return body.split(".", 1)[0]


def _column_of(document_id: str) -> str | None:
    kind, body = document_id.split(":", 1)
    return body.split(".", 1)[1] if kind == "column" else None


class Retriever:
    def __init__(
        self,
        documents: list[SchemaDocument],
        schema_index: SchemaIndex,
        value_index: ValueIndex,
        table_db: dict[str, str],
    ):
        self.documents = {d.id: d for d in documents}
        self.schema_index = schema_index
        self.value_index = value_index
        self.table_db = table_db
        self.bm25 = BM25({d.id: d.text for d in documents})

    def retrieve(self, question: str, limit: int = 30, db_id: str | None = None) -> list[TableCandidate]:
        ranks: dict[str, dict[str, int]] = defaultdict(dict)
        for position, hit in enumerate(
            self.schema_index.search(question, limit=CANDIDATE_DEPTH, db_id=db_id)
        ):
            ranks[hit.id]["vector"] = position
        for position, hit in enumerate(self.bm25.search(question, limit=CANDIDATE_DEPTH)):
            if db_id is None or self.table_db.get(_table_of(hit.id)) == db_id:
                ranks[hit.id]["keyword"] = position

        value_hits = defaultdict(list)
        for position, hit in enumerate(self.value_index.lookup(question, limit=20)):
            if db_id is not None and self.table_db.get(hit.table) != db_id:
                continue
            document_id = f"column:{hit.table}.{hit.column}"
            if document_id in self.documents:
                ranks[document_id].setdefault("value", position)
                value_hits[hit.table].append(f"{hit.column}={hit.value}")

        table_scores: dict[str, float] = defaultdict(float)
        table_columns: dict[str, list[str]] = defaultdict(list)
        table_sources: dict[str, set[str]] = defaultdict(set)
        for document_id, positions in ranks.items():
            table = _table_of(document_id)
            table_scores[table] += sum(1 / (RRF_K + position + 1) for position in positions.values())
            table_sources[table].update(positions)
            column = _column_of(document_id)
            if column:
                table_columns[table].append(column)

        ranked = sorted(table_scores.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
        return [
            TableCandidate(
                table=table,
                db_id=self.table_db.get(table, ""),
                score=round(score, 6),
                columns=table_columns[table][:10],
                values=value_hits.get(table, [])[:5],
                sources=sorted(table_sources[table]),
            )
            for table, score in ranked
        ]
