import pytest

from sqlagent.index.embeddings import SchemaDocument, SchemaIndex
from sqlagent.index.values import ValueIndex
from sqlagent.retrieval.retriever import Retriever

DOCUMENTS = [
    SchemaDocument(
        "table:account",
        "table account: bank accounts",
        {"kind": "table", "db_id": "financial", "table": "account", "column": ""},
    ),
    SchemaDocument(
        "column:account.frequency",
        "column account.frequency: how often statements are issued",
        {"kind": "column", "db_id": "financial", "table": "account", "column": "frequency"},
    ),
    SchemaDocument(
        "table:customers",
        "table customers: debit card customers",
        {"kind": "table", "db_id": "debit", "table": "customers", "column": ""},
    ),
    SchemaDocument(
        "column:customers.currency",
        "column customers.currency: payment currency",
        {"kind": "column", "db_id": "debit", "table": "customers", "column": "currency"},
    ),
]
TABLE_DB = {"account": "financial", "customers": "debit"}
VALUES = ValueIndex({"customers.currency": ["EUR", "CZK"]})


@pytest.fixture
def retriever(tmp_path, fake_embedder):
    index = SchemaIndex(fake_embedder, path=tmp_path / "chroma")
    index.rebuild(DOCUMENTS)
    return Retriever(DOCUMENTS, index, VALUES, TABLE_DB)


def test_keyword_match_finds_the_table(retriever):
    top = retriever.retrieve("how often are statements issued")[0]
    assert top.table == "account"
    assert "frequency" in top.columns
    assert "keyword" in top.sources


def test_value_match_adds_evidence(retriever):
    hits = {c.table: c for c in retriever.retrieve("customers paying in EUR")}
    assert hits["customers"].values == ["currency=EUR"]
    assert "value" in hits["customers"].sources


def test_database_filter_limits_candidates(retriever):
    tables = {c.table for c in retriever.retrieve("statements paid in EUR", db_id="financial")}
    assert tables == {"account"}


def test_limit_and_scores_are_ordered(retriever):
    candidates = retriever.retrieve("currency", limit=1)
    assert len(candidates) == 1
    ordered = retriever.retrieve("currency", limit=10)
    assert [c.score for c in ordered] == sorted((c.score for c in ordered), reverse=True)
    assert ordered[0].db_id == TABLE_DB[ordered[0].table]


def test_unmatched_question_returns_ranked_vector_results(retriever):
    assert retriever.retrieve("zzz qqq") != []


def test_value_hits_for_unknown_columns_are_ignored(tmp_path, fake_embedder):
    index = SchemaIndex(fake_embedder, path=tmp_path / "chroma")
    index.rebuild(DOCUMENTS)
    values = ValueIndex({"ghost.col": ["EUR"], "customers.currency": ["EUR"]})
    retriever = Retriever(DOCUMENTS, index, values, TABLE_DB)
    assert "ghost" not in {c.table for c in retriever.retrieve("paying in EUR")}
