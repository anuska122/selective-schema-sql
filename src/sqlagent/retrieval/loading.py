import json
from pathlib import Path

from sqlagent.index import embeddings as emb
from sqlagent.index.build import INDEX_DIR, TABLE_MAP
from sqlagent.index.fk_graph import FKGraph
from sqlagent.index.values import ValueIndex
from sqlagent.retrieval.retriever import Retriever


def load_retriever(
    index_dir: Path = INDEX_DIR, table_map: Path = TABLE_MAP, embedder: emb.Embedder | None = None
) -> Retriever:
    documents = emb.load_documents(index_dir / "documents.json")
    value_index = ValueIndex.load(index_dir / "values.json")
    schema_index = emb.SchemaIndex(
        embedder or emb.FastEmbedEmbedder(), path=index_dir / "chroma", require_existing=True
    )
    schema_index.assert_matches(documents)
    table_db = json.loads(table_map.read_text())["table_to_db"]
    if any(table_db.get(d.metadata["table"]) != d.metadata["db_id"] for d in documents):
        raise RuntimeError("schema documents disagree with the table map; rebuild the index")
    manifest_path = index_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if (
            manifest["embeddings"] != schema_index.manifest(documents)
            or manifest["values_sha256"] != value_index.content_hash()
            or manifest["fk_graph_sha256"] != FKGraph.load(index_dir / "fk_graph.json").content_hash()
        ):
            raise RuntimeError("schema index manifest does not match its artifacts; rebuild the index")
    return Retriever(documents, schema_index, value_index, table_db)
