import json

import pytest

from sqlagent.db import QueryResult
from sqlagent.index.fk_graph import FKGraph, ForeignKey, load_foreign_keys


def fk(name, table, col, ref_table, ref_col):
    return ForeignKey(name, table, (col,), ref_table, (ref_col,))


# account - district - client, disp -> account/client, card -> disp; loan -> account; island: zip
FKS = [
    fk("account_district", "account", "district_id", "district", "district_id"),
    fk("client_district", "client", "district_id", "district", "district_id"),
    fk("disp_account", "disp", "account_id", "account", "account_id"),
    fk("disp_client", "disp", "client_id", "client", "client_id"),
    fk("card_disp", "card", "disp_id", "disp", "disp_id"),
    fk("loan_account", "loan", "account_id", "account", "account_id"),
    fk("hero_eye", "superhero", "eye_colour_id", "colour", "id"),
    fk("hero_hair", "superhero", "hair_colour_id", "colour", "id"),
]
GRAPH = FKGraph(FKS, tables=["zip_code"])


def test_join_path_shortest():
    assert GRAPH.join_path("card", "district") in (
        ["card", "disp", "account", "district"],
        ["card", "disp", "client", "district"],
    )
    assert GRAPH.join_path("loan", "account") == ["loan", "account"]
    assert GRAPH.join_path("loan", "loan") == ["loan"]


def test_join_path_is_deterministic():
    assert GRAPH.join_path("card", "district") == FKGraph(list(reversed(FKS)), ["zip_code"]).join_path(
        "card", "district"
    )


def test_unreachable_tables():
    assert GRAPH.join_path("loan", "colour") is None
    assert GRAPH.join_path("zip_code", "loan") is None
    assert GRAPH.join_path("nope", "loan") is None


def test_parallel_foreign_keys_are_all_kept():
    names = {f.name for f in GRAPH.edges_between("colour", "superhero")}
    assert names == {"hero_eye", "hero_hair"}
    assert GRAPH.neighbors("superhero") == ["colour"]


def test_connect_adds_bridge_tables_with_fewest_joins():
    tables, joins = GRAPH.connect(["card", "loan"])
    assert tables == ["account", "card", "disp", "loan"]
    assert len(joins) == 3
    assert {frozenset(j) for j in joins} == {
        frozenset(("card", "disp")),
        frozenset(("disp", "account")),
        frozenset(("account", "loan")),
    }


def test_connect_single_and_unconnectable():
    assert GRAPH.connect(["loan"]) == (["loan"], [])
    assert GRAPH.connect(["loan", "colour"]) is None
    assert GRAPH.connect([]) is None
    assert GRAPH.connect(["missing"]) is None


def test_components_within_scope():
    assert GRAPH.components(["account", "loan", "zip_code", "colour"]) == [
        ["account", "loan"],
        ["colour"],
        ["zip_code"],
    ]


def test_join_condition_composite():
    composite = ForeignKey("c", "a", ("x", "y"), "b", ("bx", "by"))
    assert composite.join_condition() == "a.x = b.bx AND a.y = b.by"


def test_load_foreign_keys_groups_composite_and_strips_quotes():
    rows = [
        ("order_account_fkey", '"order"', "account", 1, "account_id", "account_id"),
        ("pair_fkey", "a", "b", 1, "x", "bx"),
        ("pair_fkey", "a", "b", 2, "y", "by"),
    ]
    fks = load_foreign_keys(lambda sql, **kw: QueryResult(rows=rows))
    assert fks == [
        ForeignKey("order_account_fkey", "order", ("account_id",), "account", ("account_id",)),
        ForeignKey("pair_fkey", "a", ("x", "y"), "b", ("bx", "by")),
    ]


def test_load_foreign_keys_failure():
    with pytest.raises(RuntimeError, match="introspection failed"):
        load_foreign_keys(lambda sql, **kw: QueryResult(error="x", error_type="db_error"))


def test_save_load_round_trip_and_tamper_detection(tmp_path):
    path = tmp_path / "fk.json"
    GRAPH.save(path)
    loaded = FKGraph.load(path)
    assert loaded.to_dict() == GRAPH.to_dict()
    assert loaded.content_hash() == GRAPH.content_hash()

    data = json.loads(path.read_text())
    data["foreign_keys"].pop()
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="hash mismatch"):
        FKGraph.load(path)


def test_self_referencing_key_is_an_edge_but_not_a_neighbor():
    graph = FKGraph([fk("manager", "employee", "manager_id", "employee", "id")])
    assert graph.neighbors("employee") == []
    assert [f.name for f in graph.edges_between("employee", "employee")] == ["manager"]
    assert graph.join_path("employee", "employee") == ["employee"]
