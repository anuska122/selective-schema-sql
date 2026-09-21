from sqlagent.index.fk_graph import FKGraph, ForeignKey
from sqlagent.lineage import query_lineage

GRAPH = FKGraph(
    [
        ForeignKey("eye", "superhero", ("eye_colour_id",), "colour", ("id",)),
        ForeignKey("hair", "superhero", ("hair_colour_id",), "colour", ("id",)),
        ForeignKey("pub", "superhero", ("publisher_id",), "publisher", ("id",), source="inferred"),
    ]
)
SQL = "SELECT COUNT(*) FROM superhero s JOIN colour c ON s.eye_colour_id = c.id WHERE c.colour = 'Blue'"


def test_joins_between_used_tables_include_every_foreign_key():
    lineage = query_lineage(SQL, ["colour", "superhero"], GRAPH)
    assert {(j["from"], j["from_columns"][0], j["to"], j["to_columns"][0]) for j in lineage["joins"]} == {
        ("superhero", "eye_colour_id", "colour", "id"),
        ("superhero", "hair_colour_id", "colour", "id"),
    }
    assert all(j["inferred"] is False for j in lineage["joins"])


def test_inferred_keys_are_marked():
    joins = query_lineage("SELECT 1", ["superhero", "publisher"], GRAPH)["joins"]
    assert joins == [
        {
            "from": "superhero",
            "from_columns": ["publisher_id"],
            "to": "publisher",
            "to_columns": ["id"],
            "inferred": True,
        }
    ]


def test_columns_used_per_table():
    columns = query_lineage(SQL, ["colour", "superhero"], GRAPH)["columns"]
    assert columns == {"colour": ["colour", "id"], "superhero": ["eye_colour_id"]}


def test_unqualified_columns_go_to_the_only_table():
    columns = query_lineage("SELECT colour FROM colour WHERE id = 1", ["colour"], GRAPH)["columns"]
    assert columns == {"colour": ["colour", "id"]}


def test_missing_or_broken_sql_still_returns_joins():
    for sql in (None, "SELEC nonsense ((("):
        lineage = query_lineage(sql, ["colour", "superhero"], GRAPH)
        assert lineage["columns"] == {}
        assert len(lineage["joins"]) == 2
