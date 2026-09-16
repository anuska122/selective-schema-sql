import json

from sqlagent.index import embeddings as emb
from sqlagent.index.values import ValueIndex
from sqlagent.retrieval.loading import load_retriever
from tests.test_retriever import DOCUMENTS, TABLE_DB


def test_load_retriever_reads_a_built_index(tmp_path, fake_embedder):
    index_dir = tmp_path / "index"
    emb.save_documents(DOCUMENTS, index_dir / "documents.json")
    ValueIndex({"customers.currency": ["EUR"]}).save(index_dir / "values.json")
    emb.SchemaIndex(fake_embedder, path=index_dir / "chroma").rebuild(DOCUMENTS)
    table_map = tmp_path / "map.json"
    table_map.write_text(json.dumps({"table_to_db": TABLE_DB}))

    retriever = load_retriever(index_dir=index_dir, table_map=table_map, embedder=fake_embedder)

    assert len(retriever.documents) == len(DOCUMENTS)
    assert retriever.retrieve("customers paying in EUR")[0].table == "customers"
