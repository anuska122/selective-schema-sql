import pytest
from conftest import FakeEmbedder

from sqlagent.index.descriptions import TableDescription
from sqlagent.index.embeddings import SchemaIndex, build_documents, table_documents


def description(table, columns, text="what it stores"):
    return TableDescription(table, text, columns, "sha", "model")


TYPES = {"account_id": "bigint", "frequency": "text"}


def test_table_documents_cover_table_and_every_column():
    docs = table_documents("financial", description("account", {"account_id": "the id"}), TYPES)
    assert [d.id for d in docs] == ["table:account", "column:account.account_id", "column:account.frequency"]
    assert docs[0].metadata == {"kind": "table", "db_id": "financial", "table": "account", "column": ""}
    assert "table account in database financial: what it stores" in docs[0].text
    assert "columns: account_id" in docs[0].text
    assert docs[1].text == "column account.account_id (bigint) in database financial: the id"
    assert docs[2].text.endswith("(text) in database financial:")


def test_build_documents_skips_tables_without_descriptions():
    docs = build_documents(
        {"financial": ["account", "loan"]},
        {"account": description("account", {"account_id": "id"})},
        {"account": TYPES},
    )
    assert {d.metadata["table"] for d in docs} == {"account"}


@pytest.fixture
def index(tmp_path):
    return SchemaIndex(FakeEmbedder(), path=tmp_path / "chroma")


DOCS = build_documents(
    {"financial": ["account"], "superhero": ["colour"]},
    {
        "account": description("account", {"account_id": "id", "frequency": "how often"}),
        "colour": description("colour", {"id": "id", "colour": "colour name"}),
    },
    {"account": TYPES, "colour": {"id": "bigint", "colour": "text"}},
)


def test_rebuild_is_repeatable_and_reports_model(index):
    report = index.rebuild(DOCS)
    assert report["documents"] == len(DOCS) == 6
    assert report["embedding_model"] == "fake-embedder"
    assert index.size == 6
    index.rebuild(DOCS[:3])
    assert index.size == 3


def test_search_returns_ranked_hits_with_metadata(index):
    index.rebuild(DOCS)
    hits = index.search("column account.frequency (text) in database financial: how often", limit=3)
    assert hits[0].id == "column:account.frequency"
    assert (hits[0].kind, hits[0].db_id, hits[0].table, hits[0].column) == (
        "column",
        "financial",
        "account",
        "frequency",
    )
    assert hits[0].score == pytest.approx(1.0, abs=1e-3)
    assert len(hits) == 3


def test_search_filters_by_kind_and_database(index):
    index.rebuild(DOCS)
    assert {h.kind for h in index.search("anything", limit=10, kind="table")} == {"table"}
    assert {h.db_id for h in index.search("anything", limit=10, db_id="superhero")} == {"superhero"}
    both = index.search("anything", limit=10, kind="table", db_id="superhero")
    assert [(h.table, h.column) for h in both] == [("colour", None)]


def test_progress_callback_and_manifest(index):
    seen = []
    index.rebuild(DOCS, progress=lambda done, total: seen.append((done, total)))
    assert seen == [(6, 6)]
    manifest = index.manifest(DOCS)
    assert manifest["documents"] == 6
    assert manifest["embedding_model"] == "fake-embedder"
    assert len(manifest["sha256"]) == 64
    assert manifest["sha256"] != index.manifest(DOCS[:3])["sha256"]


def test_index_persists_between_instances(tmp_path):
    path = tmp_path / "chroma"
    SchemaIndex(FakeEmbedder(), path=path).rebuild(DOCS)
    assert SchemaIndex(FakeEmbedder(), path=path).size == 6
