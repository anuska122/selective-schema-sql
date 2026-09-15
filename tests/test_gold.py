from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from sqlagent.db import QueryResult
from sqlagent.eval.dataset import Question
from sqlagent.eval.gold import compute_gold, decode_value, encode_value, load_gold, save_gold, sql_hash


def q(qid, sql="SELECT 1"):
    return Question(qid, "db", "question", "", sql, "simple")


@pytest.mark.parametrize(
    "value",
    [
        None,
        1,
        2.5,
        "text",
        True,
        Decimal("3.140"),
        date(2024, 1, 2),
        datetime(2024, 1, 2, 3, 4, 5),
        time(3, 4, 5),
        timedelta(hours=1, seconds=3),
        b"\x00\xff",
    ],
)
def test_value_round_trip_preserves_type_and_value(value):
    decoded = decode_value(encode_value(value))
    assert decoded == value
    assert type(decoded) is type(value)


def fake_execute(results):
    def execute(query, *, caller, question_id):
        return results[question_id]

    return execute


def test_compute_save_load_round_trip(tmp_path):
    questions = [q(1), q(2, "SELECT 2")]
    execute = fake_execute(
        {
            1: QueryResult(columns=["a"], rows=[(Decimal("1.5"), None)], duration_ms=3.0),
            2: QueryResult(columns=["b"], rows=[("x",), ("y",)], duration_ms=4.0),
        }
    )
    results, failures = compute_gold(questions, execute)
    assert failures == []

    path = tmp_path / "gold.json"
    save_gold(results, path)
    loaded = load_gold(questions, path)
    assert loaded == results
    assert set(loaded[2].rows) == {("x",), ("y",)}


def test_failed_and_truncated_gold_are_reported_not_cached():
    questions = [q(1), q(2), q(3)]
    execute = fake_execute(
        {
            1: QueryResult(rows=[(1,)]),
            2: QueryResult(error="boom", error_type="timeout"),
            3: QueryResult(rows=[(1,)], truncated=True),
        }
    )
    results, failures = compute_gold(questions, execute)
    assert list(results) == [1]
    assert failures == ["2: timeout: boom", "3: gold result exceeds the row cap"]


def test_load_detects_changed_gold_sql(tmp_path):
    path = tmp_path / "gold.json"
    results, _ = compute_gold([q(1)], fake_execute({1: QueryResult(rows=[(1,)])}))
    save_gold(results, path)
    with pytest.raises(ValueError, match="changed"):
        load_gold([q(1, "SELECT 999")], path)


def test_load_detects_missing_question(tmp_path):
    path = tmp_path / "gold.json"
    save_gold({}, path)
    with pytest.raises(KeyError, match="rebuild"):
        load_gold([q(1)], path)


def test_sql_hash_is_stable():
    assert sql_hash("SELECT 1") == sql_hash("SELECT 1") != sql_hash("SELECT 2")
