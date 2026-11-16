import pytest

from scripts.analyze_errors import classify


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"correct": True}, "correct"),
        ({"correct": False, "exec_error": "strategy_error: failure"}, "strategy_error"),
        ({"correct": False, "details": {"retrieved": ["other"]}}, "retrieval_miss"),
        ({"correct": False, "details": {"retrieved": ["account"], "selected": ["other"]}}, "selection_miss"),
        ({"correct": False, "pred_sql": None}, "no_valid_sql"),
        ({"correct": False, "pred_sql": "SELECT 1", "exec_error": "db_error: failure"}, "execution_error"),
        ({"correct": False, "pred_sql": "SELECT 1"}, "wrong_result"),
        (
            {"correct": False, "pred_sql": "SELECT 1", "details": {"selected": [], "widened": ["account"]}},
            "wrong_result",
        ),
    ],
)
def test_error_classification(row, expected):
    assert classify(row, {"account"}) == expected


def test_legacy_truncated_candidate_lists_do_not_prove_retrieval_misses():
    row = {"correct": False, "pred_sql": "SELECT 1", "details": {"candidates": ["other"]}}
    assert classify(row, {"account"}) == "wrong_result"
