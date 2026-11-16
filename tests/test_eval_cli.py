import json
import sys

from scripts import cache_gold, run_eval
from sqlagent.eval.dataset import Question
from sqlagent.eval.gold import GoldResult, sql_hash

QUESTION = Question(1, "db", "question", "", "SELECT 1", "simple")


def test_full_dataset_cli_uses_separate_cache_and_records_scoring(monkeypatch, tmp_path):
    cache = tmp_path / "reference.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_eval", "gold_oracle", "--all", "--gold-cache", str(cache), "--comparison", "ordered"],
    )
    monkeypatch.setattr(run_eval, "load_questions", lambda: [QUESTION])
    monkeypatch.setattr(run_eval, "load_gold", lambda questions, path: {"path": path})
    seen = {}

    def evaluate(strategy, questions, gold, **kwargs):
        seen.update(questions=questions, gold=gold, **kwargs)
        (tmp_path / "summary.json").write_text(json.dumps({"overall": {"n": 1}}))
        return tmp_path

    monkeypatch.setattr(run_eval, "run_eval", evaluate)
    assert run_eval.main() == 0
    assert seen["questions"] == [QUESTION]
    assert seen["gold"] == {"path": cache}
    assert seen["comparison"] == "ordered"
    assert seen["sample_path"] == run_eval.DATASET


def test_full_gold_cache_is_separate_from_frozen_sample(monkeypatch, tmp_path):
    path = tmp_path / "all.json"
    monkeypatch.setattr(sys, "argv", ["cache_gold", "--all", "--output", str(path)])
    monkeypatch.setattr(cache_gold, "load_questions", lambda: [QUESTION])
    monkeypatch.setattr(
        cache_gold,
        "compute_gold",
        lambda questions: ({1: GoldResult(1, sql_hash(QUESTION.gold_sql), ["x"], [(1,)], 1.0)}, []),
    )
    assert cache_gold.main() == 0
    assert json.loads(path.read_text())["1"]["rows"] == [[1]]


def test_unusable_gold_does_not_overwrite_a_cache(monkeypatch, tmp_path):
    path = tmp_path / "all.json"
    path.write_text("existing cache")
    monkeypatch.setattr(sys, "argv", ["cache_gold", "--all", "--output", str(path)])
    monkeypatch.setattr(cache_gold, "load_questions", lambda: [QUESTION])
    monkeypatch.setattr(cache_gold, "compute_gold", lambda questions: ({}, ["1: timeout"]))
    assert cache_gold.main() == 1
    assert path.read_text() == "existing cache"


def test_row_cap_mismatch_is_rejected_before_model_initialization(monkeypatch, tmp_path):
    import pytest

    cache = tmp_path / "all.json"
    cache.with_suffix(".meta.json").write_text(json.dumps({"max_rows": 50000}))
    monkeypatch.setattr(sys, "argv", ["run_eval", "gold_oracle", "--all", "--gold-cache", str(cache)])
    monkeypatch.setattr(run_eval, "load_questions", lambda: [QUESTION])
    with pytest.raises(SystemExit) as stopped:
        run_eval.main()
    assert stopped.value.code == 2


def test_incomplete_cli_run_returns_nonzero_status(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys, "argv", ["run_eval", "gold_oracle", "--gold-cache", str(tmp_path / "cache.json")]
    )
    monkeypatch.setattr(run_eval, "load_sample", lambda: [QUESTION])
    monkeypatch.setattr(run_eval, "load_gold", lambda *args, **kwargs: {})
    (tmp_path / "summary.json").write_text(json.dumps({"incomplete": {"reason": "provider"}}))
    monkeypatch.setattr(run_eval, "run_eval", lambda *args, **kwargs: tmp_path)
    assert run_eval.main() == 2
