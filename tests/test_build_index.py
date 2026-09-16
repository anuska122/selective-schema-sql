import json

import pytest
from conftest import FakeEmbedder

from sqlagent.db import QueryResult
from sqlagent.index import build as build_module
from sqlagent.index.descriptions import DescriptionStore, TableDescription
from sqlagent.index.fk_graph import FKGraph, ForeignKey
from sqlagent.index.values import ValueIndex

COLUMNS = [
    ("account", "account_id", "bigint"),
    ("account", "frequency", "text"),
    ("loan", "loan_id", "bigint"),
]


def fake_execute(sql, *, caller, question_id, **kw):
    if "information_schema.columns" in sql:
        return QueryResult(rows=COLUMNS)
    if "pg_get_keywords" in sql:
        return QueryResult(rows=[("order",)])
    raise AssertionError(f"unexpected query: {sql}")


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    table_map = tmp_path / "map.json"
    table_map.write_text(json.dumps({"databases": {"financial": {"account": 1, "loan": 2}}}))
    declared = [ForeignKey("fk", "loan", ("account_id",), "account", ("account_id",))]
    inferred = [ForeignKey("inferred:x", "loan", ("x",), "account", ("y",), source="inferred", coverage=1.0)]
    monkeypatch.setattr(build_module, "load_foreign_keys", lambda execute: declared)
    monkeypatch.setattr(build_module, "infer_foreign_keys", lambda *a, **k: (inferred, [{"c": 1}, {"c": 2}]))
    monkeypatch.setattr(
        build_module,
        "build_value_index",
        lambda reserved, execute: (
            ValueIndex({"account.frequency": ["monthly"]}),
            {"values": 1, "indexed_columns": 1},
        ),
    )
    return tmp_path, table_map


def describe_all(index_dir):
    store = DescriptionStore(index_dir / "descriptions.json")
    for table, columns in (
        ("account", {"account_id": "id", "frequency": "how often"}),
        ("loan", {"loan_id": "id"}),
    ):
        store.put(
            TableDescription(
                table,
                f"the {table} table",
                columns,
                "sha",
                "openai/gpt-oss-20b",
                tokens_in=100,
                tokens_out=50,
            )
        )
    return store


def test_build_writes_every_artifact_and_manifest(prepared):
    index_dir, table_map = prepared
    describe_all(index_dir)
    logs = []

    manifest = build_module.build(
        index_dir=index_dir,
        table_map=table_map,
        execute=fake_execute,
        embedder=FakeEmbedder(),
        log=logs.append,
    )

    assert (index_dir / "fk_graph.json").exists()
    assert (index_dir / "values.json").exists()
    assert (index_dir / "manifest.json").exists()
    assert manifest == json.loads((index_dir / "manifest.json").read_text())
    assert manifest["tables"] == 2
    assert manifest["columns"] == 3
    assert manifest["foreign_keys"] == {"declared": 1, "inferred": 1, "candidates": 2}
    assert manifest["embeddings"]["documents"] == 5
    assert manifest["embeddings"]["embedding_model"] == "fake-embedder"
    assert manifest["descriptions"]["tables"] == 2
    assert manifest["offline_cost"]["llm_tokens_in"] == 200
    assert manifest["offline_cost"]["models"] == ["openai/gpt-oss-20b"]
    assert manifest["offline_cost"]["list_price_usd"] > 0
    assert len(manifest["content_sha256"]) == 64
    assert FKGraph.load(index_dir / "fk_graph.json").content_hash() == manifest["fk_graph_sha256"]
    assert any("foreign keys" in line for line in logs)


def test_build_is_reproducible_and_hash_tracks_content(prepared):
    index_dir, table_map = prepared
    describe_all(index_dir)
    kwargs = {"index_dir": index_dir, "table_map": table_map, "execute": fake_execute, "log": lambda _: None}
    first = build_module.build(embedder=FakeEmbedder(), **kwargs)
    second = build_module.build(embedder=FakeEmbedder(), **kwargs)
    assert first["content_sha256"] == second["content_sha256"]

    store = DescriptionStore(index_dir / "descriptions.json")
    store.put(
        TableDescription("account", "different text", {"account_id": "id"}, "sha", "openai/gpt-oss-20b")
    )
    third = build_module.build(embedder=FakeEmbedder(), **kwargs)
    assert third["content_sha256"] != first["content_sha256"]


def test_build_refuses_when_descriptions_are_missing(prepared):
    index_dir, table_map = prepared
    with pytest.raises(RuntimeError, match="no description"):
        build_module.build(
            index_dir=index_dir,
            table_map=table_map,
            execute=fake_execute,
            embedder=FakeEmbedder(),
            log=lambda _: None,
        )


@pytest.mark.parametrize("failing", ["information_schema.columns", "pg_get_keywords"])
def test_build_fails_loudly_on_introspection_errors(prepared, failing):
    index_dir, table_map = prepared

    def execute(sql, **kw):
        if failing in sql:
            return QueryResult(error="denied", error_type="db_error")
        return fake_execute(sql, **kw)

    with pytest.raises(RuntimeError, match="failed"):
        build_module.build(
            index_dir=index_dir,
            table_map=table_map,
            execute=execute,
            embedder=FakeEmbedder(),
            log=lambda _: None,
        )
