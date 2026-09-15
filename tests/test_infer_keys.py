import re

import pytest

from sqlagent.db import QueryResult
from sqlagent.index.fk_graph import FKGraph, ForeignKey
from sqlagent.index.infer_keys import (
    Column,
    candidates,
    infer_foreign_keys,
    match_rule,
    singular,
    type_family,
)

RESERVED = {"order"}


def col(table, name, data_type="bigint"):
    return Column(table, name, data_type)


@pytest.mark.parametrize(
    ("child", "parent", "rule"),
    [
        (col("yearmonth", "customerid"), col("customers", "customerid"), "same_name"),
        (col("legalities", "uuid", "text"), col("cards", "uuid", "character varying"), "same_name"),
        (col("match", "league_id"), col("league", "id"), "named_after_table"),
        (col("cards", "setcode", "text"), col("sets", "code", "text"), "named_after_table"),
        (col("postlinks", "postid", "integer"), col("posts", "id", "bigint"), "named_after_table"),
        (col("a", "id"), col("b", "id"), None),
        (col("a", "name", "text"), col("b", "name", "text"), None),
        (col("a", "customerid", "text"), col("b", "customerid", "bigint"), None),
        (col("a", "total"), col("b", "count"), None),
    ],
)
def test_match_rule(child, parent, rule):
    assert match_rule(child, parent) == rule


def test_singular_and_type_family():
    assert singular("posts") == "post"
    assert singular("class") == "class"
    assert singular("league") == "league"
    assert type_family("integer") == type_family("bigint")
    assert type_family("text") == type_family("character varying")
    assert type_family("date") == "date"


def test_candidates_skip_declared_other_scopes_and_same_table():
    columns = [
        col("customers", "customerid"),
        col("yearmonth", "customerid"),
        col("orders", "customerid"),
        col("elsewhere", "customerid"),
    ]
    declared = [ForeignKey("fk", "orders", ("customerid",), "customers", ("customerid",))]
    found = candidates(columns, [["customers", "yearmonth", "orders"], ["elsewhere"]], declared)
    pairs = {(c.child.table, c.parent.table) for c in found}
    assert ("orders", "customers") not in pairs
    assert ("customers", "orders") not in pairs
    assert ("yearmonth", "customers") in pairs
    assert not any("elsewhere" in p for p in pairs)


class FakeDB:
    """Answers the two inference queries from in-memory column values."""

    def __init__(self, data):
        self.data = data
        self.queries = []

    def __call__(self, sql, *, caller, question_id, timeout_ms):
        self.queries.append(sql)
        unique = re.fullmatch(r"SELECT count\((\S+)\), count\(DISTINCT \S+\) FROM (\S+)", sql)
        if unique:
            values = [v for v in self.data[(unique[2].strip('"'), unique[1].strip('"'))] if v is not None]
            return QueryResult(rows=[(len(values), len(set(values)))])
        cov = re.search(r"DISTINCT (\S+) AS v FROM (\S+) WHERE .* DISTINCT (\S+) AS v FROM (\S+)\) p", sql)
        child = {v for v in self.data[(cov[2].strip('"'), cov[1].strip('"'))] if v is not None}
        parent = set(self.data[(cov[4].strip('"'), cov[3].strip('"'))])
        return QueryResult(rows=[(len(child), len(child & parent))])


def test_infer_accepts_verified_keys_and_rejects_the_rest():
    data = {
        ("customers", "customerid"): [1, 2, 3],
        ("yearmonth", "customerid"): [1, 1, 2, 3, None],
        ("transactions", "customerid"): [1, 9],
        ("loan", "account_id"): [7, 8],
        ("order", "account_id"): [7, 8, 8],
        ("disp", "account_id"): [7, 7, 8, 5, 6, 4, 3, 2, 1, 0],
    }
    columns = [col(t, c) for t, c in data]
    execute = FakeDB(data)
    fks, report = infer_foreign_keys(
        columns, [[t for t, _ in data]], [], RESERVED, execute=execute, min_coverage=0.95
    )
    accepted = {(f.table, f.ref_table) for f in fks}
    assert accepted == {("yearmonth", "customers"), ("order", "loan")}
    by_pair = {(r["child"], r["parent"]): r for r in report}
    assert by_pair[("transactions.customerid", "customers.customerid")]["coverage"] == 0.5
    assert by_pair[("transactions.customerid", "customers.customerid")]["accepted"] is False
    assert by_pair[("customers.customerid", "yearmonth.customerid")]["parent_unique"] is False
    assert by_pair[("disp.account_id", "loan.account_id")]["accepted"] is False
    fk = next(f for f in fks if f.table == "yearmonth")
    assert (fk.source, fk.rule, fk.coverage) == ("inferred", "same_name", 1.0)
    assert any('FROM "order"' in q for q in execute.queries)
    assert sum("count(DISTINCT" in q for q in execute.queries) == len({r["parent"] for r in report})


@pytest.mark.parametrize(
    ("a_values", "b_values", "expected_child"),
    [([1, 2], [1, 2], "a"), ([1, 2, 3], [1, 2], "b"), ([1, 2], [1, 2, 3], "a")],
)
def test_both_directions_valid_keeps_the_better_covered_edge(a_values, b_values, expected_child):
    data = {("a", "code_id"): a_values, ("b", "code_id"): b_values}
    fks, report = infer_foreign_keys(
        [col("a", "code_id"), col("b", "code_id")],
        [["a", "b"]],
        [],
        RESERVED,
        execute=FakeDB(data),
        min_coverage=0.5,
    )
    assert [f.table for f in fks] == [expected_child]
    assert sum(r["accepted"] for r in report) == 1


def test_empty_child_column_has_no_coverage():
    data = {("a", "customerid"): [None], ("b", "customerid"): [1]}
    fks, report = infer_foreign_keys(
        [col("a", "customerid"), col("b", "customerid")], [["a", "b"]], [], RESERVED, execute=FakeDB(data)
    )
    assert fks == []
    assert {r["coverage"] for r in report if r["parent"] == "b.customerid"} == {None}


def test_query_failure_raises():
    def failing(sql, **kw):
        return QueryResult(error="timeout", error_type="timeout")

    with pytest.raises(RuntimeError, match="key inference query failed"):
        infer_foreign_keys(
            [col("yearmonth", "customerid"), col("customers", "customerid")],
            [["yearmonth", "customers"]],
            [],
            RESERVED,
            execute=failing,
        )


def test_inferred_edges_round_trip_through_graph(tmp_path):
    fk = ForeignKey(
        "inferred:a.x->b.x", "a", ("x",), "b", ("x",), source="inferred", rule="same_name", coverage=1.0
    )
    path = tmp_path / "g.json"
    FKGraph([fk]).save(path)
    loaded = FKGraph.load(path).foreign_keys[0]
    assert loaded == fk
