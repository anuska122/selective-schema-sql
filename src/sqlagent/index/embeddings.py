import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import chromadb

from sqlagent import config
from sqlagent.index.descriptions import TableDescription

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
CHROMA_PATH = config.ROOT / "data" / "index" / "chroma"
COLLECTION = "schema"
BATCH_SIZE = 256


class Embedder(Protocol):
    model_name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedEmbedder:
    def __init__(self, model_name: str = EMBEDDING_MODEL):
        from fastembed import TextEmbedding

        self.model_name = model_name
        self._model = TextEmbedding(model_name=model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [vector.tolist() for vector in self._model.embed(texts)]


@dataclass(frozen=True)
class SchemaDocument:
    id: str
    text: str
    metadata: dict


@dataclass(frozen=True)
class SearchHit:
    id: str
    kind: str
    db_id: str
    table: str
    column: str | None
    score: float


def table_documents(
    db_id: str, description: TableDescription, column_types: dict[str, str]
) -> list[SchemaDocument]:
    columns = ", ".join(description.columns) or ", ".join(column_types)
    table_text = (
        f"table {description.table} in database {db_id}: {description.description} columns: {columns}"
    )
    docs = [
        SchemaDocument(
            f"table:{description.table}",
            table_text,
            {"kind": "table", "db_id": db_id, "table": description.table, "column": ""},
        )
    ]
    for column, data_type in column_types.items():
        text = (
            f"column {description.table}.{column} ({data_type}) in database {db_id}: "
            f"{description.columns.get(column, '')}".strip()
        )
        docs.append(
            SchemaDocument(
                f"column:{description.table}.{column}",
                text,
                {"kind": "column", "db_id": db_id, "table": description.table, "column": column},
            )
        )
    return docs


def build_documents(
    databases: dict[str, Iterable[str]],
    descriptions: dict[str, TableDescription],
    column_types: dict[str, dict[str, str]],
) -> list[SchemaDocument]:
    docs = []
    for db_id, tables in sorted(databases.items()):
        for table in sorted(tables):
            description = descriptions.get(table)
            if description is None:
                continue
            docs.extend(table_documents(db_id, description, column_types.get(table, {})))
    return docs


class SchemaIndex:
    def __init__(self, embedder: Embedder, path: Path = CHROMA_PATH):
        self.embedder = embedder
        self.path = path
        self._client = chromadb.PersistentClient(path=str(path))
        self._collection = self._client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}
        )

    @property
    def size(self) -> int:
        return self._collection.count()

    def rebuild(
        self, documents: list[SchemaDocument], progress: Callable[[int, int], None] | None = None
    ) -> dict:
        self._client.delete_collection(COLLECTION)
        self._collection = self._client.get_or_create_collection(
            COLLECTION, metadata={"hnsw:space": "cosine"}
        )
        for start in range(0, len(documents), BATCH_SIZE):
            batch = documents[start : start + BATCH_SIZE]
            self._collection.add(
                ids=[d.id for d in batch],
                documents=[d.text for d in batch],
                metadatas=[d.metadata for d in batch],
                embeddings=self.embedder.embed([d.text for d in batch]),
            )
            if progress:
                progress(min(start + BATCH_SIZE, len(documents)), len(documents))
        return {
            "documents": len(documents),
            "embedding_model": self.embedder.model_name,
            "path": str(self.path),
        }

    def search(
        self, query: str, limit: int = 30, kind: str | None = None, db_id: str | None = None
    ) -> list[SearchHit]:
        where = {k: v for k, v in (("kind", kind), ("db_id", db_id)) if v}
        clauses = [{k: v} for k, v in where.items()]
        result = self._collection.query(
            query_embeddings=self.embedder.embed([query]),
            n_results=limit,
            where=clauses[0] if len(clauses) == 1 else {"$and": clauses} if clauses else None,
        )
        hits = []
        for doc_id, metadata, distance in zip(
            result["ids"][0], result["metadatas"][0], result["distances"][0], strict=True
        ):
            hits.append(
                SearchHit(
                    id=doc_id,
                    kind=metadata["kind"],
                    db_id=metadata["db_id"],
                    table=metadata["table"],
                    column=metadata["column"] or None,
                    score=round(1 - distance, 4),
                )
            )
        return hits

    def manifest(self, documents: list[SchemaDocument]) -> dict:
        from sqlagent.schema import sha256

        payload = json.dumps([[d.id, d.text] for d in documents], sort_keys=True)
        return {
            "documents": len(documents),
            "embedding_model": self.embedder.model_name,
            "sha256": sha256(payload),
        }
