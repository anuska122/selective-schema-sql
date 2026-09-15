from decimal import Decimal

import pytest

from sqlagent.eval.metrics import execution_match, result_set, stage_cost_usd
from sqlagent.eval.types import StageTrace


def test_match_ignores_row_order_and_duplicates():
    assert execution_match([(1, "a"), (2, "b"), (1, "a")], [(2, "b"), (1, "a")])


def test_match_respects_column_order():
    assert not execution_match([("a", 1)], [(1, "a")])


def test_match_detects_different_values():
    assert not execution_match([(1,)], [(2,)])
    assert not execution_match([], [(1,)])


def test_numeric_types_compare_by_value():
    assert execution_match([(Decimal("3"),)], [(3,)])
    assert execution_match([(2.5,)], [(Decimal("2.5"),)])


def test_unhashable_values_are_normalised():
    rows = [([1, 2], {"b": 1, "a": [3]})]
    assert result_set(rows) == {((1, 2), '{"a": [3], "b": 1}')}
    assert execution_match(rows, [((1, 2), {"a": [3], "b": 1})])


PRICES = {"m": {"input": 1.0, "cached_input": 0.5, "output": 2.0}}


def test_cost_splits_cached_and_uncached_input():
    stage = StageTrace("gen", 1.0, llm_calls=1, model="m", tokens_in=1000, cached_tokens=400, tokens_out=100)
    assert stage_cost_usd(stage, PRICES) == pytest.approx((600 * 1.0 + 400 * 0.5 + 100 * 2.0) / 1e6)


def test_stage_without_llm_is_free_without_prices():
    assert stage_cost_usd(StageTrace("retrieve", 5.0), {}) == 0.0


def test_unknown_model_price_fails_loudly():
    with pytest.raises(KeyError, match="no price"):
        stage_cost_usd(StageTrace("gen", 1.0, llm_calls=1, model="other", tokens_in=1), PRICES)
