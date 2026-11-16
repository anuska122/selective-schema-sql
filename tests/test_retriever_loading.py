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


def make_index(path, fake_embedder, documents=DOCUMENTS):
    emb.save_documents(DOCUMENTS, path / "documents.json")
    ValueIndex({}).save(path / "values.json")
    emb.SchemaIndex(fake_embedder, path=path / "chroma").rebuild(documents)
    mapping = path / "map.json"
    mapping.write_text(json.dumps({"table_to_db": TABLE_DB}))
    return mapping


def test_missing_vector_store_is_not_silently_created(tmp_path, fake_embedder):
    import pytest

    emb.save_documents(DOCUMENTS, tmp_path / "documents.json")
    ValueIndex({}).save(tmp_path / "values.json")
    with pytest.raises(RuntimeError, match="missing"):
        load_retriever(index_dir=tmp_path, embedder=fake_embedder)
    assert not (tmp_path / "chroma").exists()


def test_empty_or_incomplete_vector_store_is_rejected(tmp_path, fake_embedder):
    import pytest

    mapping = make_index(tmp_path, fake_embedder, DOCUMENTS[:1])
    with pytest.raises(RuntimeError, match="empty or incomplete"):
        load_retriever(index_dir=tmp_path, table_map=mapping, embedder=fake_embedder)


def test_same_sized_but_stale_vector_store_is_rejected(tmp_path, fake_embedder):
    from dataclasses import replace

    import pytest

    stale = [replace(d, text="outdated " + d.text) for d in DOCUMENTS]
    mapping = make_index(tmp_path, fake_embedder, stale)
    with pytest.raises(RuntimeError, match="does not match"):
        load_retriever(index_dir=tmp_path, table_map=mapping, embedder=fake_embedder)


def test_inconsistent_table_mapping_is_rejected(tmp_path, fake_embedder):
    import pytest

    mapping = make_index(tmp_path, fake_embedder)
    mapping.write_text(json.dumps({"table_to_db": {}}))
    with pytest.raises(RuntimeError, match="table map"):
        load_retriever(index_dir=tmp_path, table_map=mapping, embedder=fake_embedder)


def test_manifest_contents_are_checked(tmp_path, fake_embedder):
    import pytest

    from sqlagent.index.fk_graph import FKGraph

    mapping = make_index(tmp_path, fake_embedder)
    graph = FKGraph([])
    graph.save(tmp_path / "fk_graph.json")
    index = emb.SchemaIndex(fake_embedder, path=tmp_path / "chroma")
    manifest = {
        "embeddings": index.manifest(DOCUMENTS),
        "values_sha256": ValueIndex({}).content_hash(),
        "fk_graph_sha256": graph.content_hash(),
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    load_retriever(index_dir=tmp_path, table_map=mapping, embedder=fake_embedder)
    manifest["embeddings"]["embedding_model"] = "different-model"
    path.write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match="manifest"):
        load_retriever(index_dir=tmp_path, table_map=mapping, embedder=fake_embedder)
