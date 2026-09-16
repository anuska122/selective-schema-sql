import json
from pathlib import Path

from sqlagent.index import embeddings as emb
from sqlagent.index.build import INDEX_DIR, TABLE_MAP
from sqlagent.index.values import ValueIndex
from sqlagent.retrieval.retriever import Retriever


def load_retriever(
    index_dir: Path = INDEX_DIR, table_map: Path = TABLE_MAP, embedder: emb.Embedder | None = None
) -> Retriever:
    documents = emb.load_documents(index_dir / "documents.json")
    value_index = ValueIndex.load(index_dir / "values.json")
    schema_index = emb.SchemaIndex(embedder or emb.FastEmbedEmbedder(), path=index_dir / "chroma")
    table_db = json.loads(table_map.read_text())["table_to_db"]
    return Retriever(documents, schema_index, value_index, table_db)
