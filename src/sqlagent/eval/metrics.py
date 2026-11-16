import json
from collections import Counter

from sqlagent.eval.types import StageTrace

COMPARISONS = ("set", "multiset", "ordered")


def _hashable(value):
    if isinstance(value, list | tuple):
        return tuple(_hashable(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, default=str)
    return value


def result_set(rows: list[tuple]) -> set[tuple]:
    return {tuple(_hashable(v) for v in row) for row in rows}


def execution_match(predicted: list[tuple], gold: list[tuple], *, comparison: str = "set") -> bool:
    """Legacy set scoring, duplicate-aware multiset scoring, or exact row ordering."""
    if comparison == "set":
        return result_set(predicted) == result_set(gold)
    normalised = [tuple(_hashable(v) for v in row) for row in predicted]
    expected = [tuple(_hashable(v) for v in row) for row in gold]
    if comparison == "multiset":
        return Counter(normalised) == Counter(expected)
    if comparison == "ordered":
        return normalised == expected
    raise ValueError(f"unknown comparison: {comparison}")


def stage_cost_usd(stage: StageTrace, prices: dict[str, dict[str, float]]) -> float:
    if stage.llm_calls == 0 and stage.tokens_in == 0 and stage.tokens_out == 0:
        return 0.0
    if stage.model not in prices:
        raise KeyError(f"no price for model {stage.model!r}; add it to the run's price table")
    p = prices[stage.model]
    uncached = stage.tokens_in - stage.cached_tokens
    return (
        uncached * p["input"] + stage.cached_tokens * p["cached_input"] + stage.tokens_out * p["output"]
    ) / 1_000_000
