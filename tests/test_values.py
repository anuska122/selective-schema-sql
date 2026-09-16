import json
import re

import pytest

from sqlagent.db import QueryResult
from sqlagent.index import values
from sqlagent.index.values import ValueIndex, build_value_index, tokenize

INDEX = ValueIndex(
    {
        "customers.segment": ["SME", "LAM", "KAM"],
        "customers.currency": ["CZK", "EUR"],
        "sets.name": ["Tenth Edition", "Ice Age", "Fifth Edition"],
        "patient.sex": ["F", "M"],
        "drivers.surname": ["Hamilton", "Schumacher", "!!!"],
    }
)


def test_tokenize():
    assert tokenize("Tenth-Edition, 10th!") == ["tenth", "edition", "10th"]


def test_lookup_exact_single_token_value():
    hits = INDEX.lookup("How many customers pay in CZK?")
    top = hits[0]
    assert (top.table, top.column, top.value, top.score) == ("customers", "currency", "CZK", 1.0)


def test_lookup_multi_token_value_needs_most_of_its_weight():
    names = [h.value for h in INDEX.lookup("cards printed in the Tenth Edition set")]
    assert names[0] == "Tenth Edition"
    assert "Fifth Edition" not in names


def test_lookup_ignores_values_without_tokens_and_respects_limits():
    assert INDEX.lookup("") == []
    assert all(h.value != "!!!" for h in INDEX.lookup("!!! hamilton"))
    assert len(INDEX.lookup("SME LAM KAM EUR CZK", limit=2)) == 2


def test_lookup_cannot_bridge_synonyms():
    assert INDEX.lookup("how many female patients") == []


def test_size_hash_and_round_trip(tmp_path):
    assert INDEX.size == 13
    path = tmp_path / "values.json"
    INDEX.save(path)
    loaded = ValueIndex.load(path)
    assert loaded.columns == INDEX.columns
    assert loaded.lookup("EUR") == INDEX.lookup("EUR")

    data = json.loads(path.read_text())
    data["columns"]["customers.currency"].append("USD")
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="hash mismatch"):
        ValueIndex.load(path)


class FakeDB:
    def __init__(self, columns, stats, data):
        self.columns, self.stats, self.data = columns, stats, data
        self.distinct_queries = []

    def __call__(self, sql, *, caller, question_id, timeout_ms):
        if "information_schema.columns" in sql:
            return QueryResult(rows=self.columns)
        if "pg_stats" in sql:
            return QueryResult(rows=self.stats)
        m = re.fullmatch(r"SELECT DISTINCT (\S+) FROM (\S+) WHERE \S+ IS NOT NULL LIMIT (\d+)", sql)
        self.distinct_queries.append(sql)
        key = (m[2].strip('"'), m[1].strip('"'))
        distinct = sorted({v for v in self.data[key] if v is not None})
        return QueryResult(rows=[(v,) for v in distinct[: int(m[3])]])


def test_build_selects_low_cardinality_columns(monkeypatch):
    monkeypatch.setattr(values, "MAX_VALUE_CHARS", 10)
    columns = [
        ("customers", "segment"),
        ("customers", "notes"),
        ("colour", "colour"),
        ("order", "status"),
        ("users", "displayname"),
        ("posts", "body"),
        ("event", "notes"),
    ]
    stats = [
        ("customers", "segment", 3.0, 100.0),
        ("customers", "notes", 2.0, 100.0),
        ("order", "status", -0.01, 400.0),
        ("users", "displayname", -1.0, 50_000.0),
        ("posts", "body", 5.0, 10.0),
        ("event", "notes", 1.0, 1.0),
    ]
    data = {
        ("customers", "segment"): ["SME", "LAM", "SME", None],
        ("customers", "notes"): ["short", "this note is far too long"],
        ("colour", "colour"): ["Red", "Blue"],
        ("order", "status"): ["A", "B", "C", "D"],
        ("posts", "body"): ["one", "two", "three", "four"],
        ("event", "notes"): ["an extremely long note"],
    }
    execute = FakeDB(columns, stats, data)
    index, report = build_value_index({"order"}, execute=execute, max_distinct=3)

    assert index.columns == {
        "colour.colour": ["Blue", "Red"],
        "customers.notes": ["short"],
        "customers.segment": ["LAM", "SME"],
    }
    assert report == {
        "text_columns": 7,
        "no_statistics": 1,
        "skipped_high_cardinality": 3,
        "dropped_long_values": 2,
        "indexed_columns": 3,
        "values": 5,
        "max_distinct": 3,
    }
    assert not any("users" in q for q in execute.distinct_queries)
    assert any('FROM "order"' in q for q in execute.distinct_queries)


def test_query_failure_raises():
    def failing(sql, **kw):
        return QueryResult(error="denied", error_type="db_error")

    with pytest.raises(RuntimeError, match="value index query failed"):
        build_value_index(set(), execute=failing)
