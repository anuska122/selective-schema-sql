import json
import subprocess

import pytest

from sqlagent.db import QueryResult
from sqlagent.eval import runner
from sqlagent.eval.dataset import Question
from sqlagent.eval.gold import GoldResult
from sqlagent.eval.types import Prediction, StageTrace
from sqlagent.strategies.oracle import GoldOracle

QUESTIONS = [
    Question(1, "db", "q1", "", "SELECT 1", "simple"),
    Question(2, "db", "q2", "", "SELECT 2", "moderate"),
]
GOLD = {
    1: GoldResult(1, "h1", ["x"], [(1,)], 1.0),
    2: GoldResult(2, "h2", ["x"], [(2,), (3,)], 1.0),
}
PRICES = {"m": {"input": 1.0, "cached_input": 0.5, "output": 2.0}}


def fake_execute(results):
    calls = []

    def execute(query, *, caller, question_id):
        calls.append((query, caller, question_id))
        return results[query]

    execute.calls = calls
    return execute


class Scripted:
    name = "scripted"
    config = {"model": "m"}

    def __init__(self, answers):
        self.answers = answers

    def answer(self, question):
        answer = self.answers[question.question_id]
        if isinstance(answer, Exception):
            raise answer
        return answer


def read_results(run_dir):
    return [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]


def test_oracle_scores_everything_correct(tmp_path):
    execute = fake_execute({"SELECT 1": QueryResult(rows=[(1,)]), "SELECT 2": QueryResult(rows=[(3,), (2,)])})
    run_dir = runner.run_eval(GoldOracle(), QUESTIONS, GOLD, runs_dir=tmp_path, execute=execute)
    rows = read_results(run_dir)
    assert [r["correct"] for r in rows] == [True, True]
    assert [c[1] for c in execute.calls] == ["gold_oracle", "gold_oracle"]
    assert run_dir.name.endswith("_gold_oracle")


def test_results_row_fields_tokens_and_cost(tmp_path):
    stage = StageTrace("gen", 12.0, llm_calls=1, model="m", tokens_in=1000, cached_tokens=200, tokens_out=50)
    strategy = Scripted({1: Prediction("SELECT 1", [stage]), 2: Prediction("SELECT 9", [stage])})
    execute = fake_execute({"SELECT 1": QueryResult(rows=[(1,)]), "SELECT 9": QueryResult(rows=[(9,)])})
    run_dir = runner.run_eval(strategy, QUESTIONS, GOLD, prices=PRICES, runs_dir=tmp_path, execute=execute)
    first, second = read_results(run_dir)
    assert first["correct"] is True
    assert second["correct"] is False
    assert second["exec_error"] is None
    assert first["tokens_in"] == 1000
    assert first["cached_tokens"] == 200
    assert first["llm_calls"] == 1
    assert first["cost_usd"] == pytest.approx((800 + 200 * 0.5 + 50 * 2) / 1e6)
    assert first["stages"][0]["name"] == "gen"
    assert set(first) >= {
        "qid",
        "db_id",
        "difficulty",
        "pred_sql",
        "exec_error",
        "correct",
        "rows_returned",
        "truncated",
        "tokens_in",
        "tokens_out",
        "cached_tokens",
        "latency_ms",
        "cost_usd",
    }


def test_errors_count_as_wrong(tmp_path):
    strategy = Scripted({1: RuntimeError("model down"), 2: Prediction("SELECT bad")})
    execute = fake_execute({"SELECT bad": QueryResult(error="boom", error_type="db_error")})
    rows = read_results(runner.run_eval(strategy, QUESTIONS, GOLD, runs_dir=tmp_path, execute=execute))
    assert rows[0]["correct"] is False
    assert rows[0]["exec_error"] == "strategy_error: RuntimeError: model down"
    assert rows[1]["correct"] is False
    assert rows[1]["exec_error"] == "db_error: boom"
    assert len(execute.calls) == 1


def test_no_sql_and_truncated_are_wrong(tmp_path):
    strategy = Scripted({1: Prediction(None), 2: Prediction("SELECT big")})
    execute = fake_execute({"SELECT big": QueryResult(rows=[(2,), (3,)], truncated=True)})
    rows = read_results(runner.run_eval(strategy, QUESTIONS, GOLD, runs_dir=tmp_path, execute=execute))
    assert rows[0]["exec_error"] == "no_sql"
    assert rows[1]["truncated"] is True
    assert rows[1]["correct"] is False


def test_config_records_reproducibility_metadata(tmp_path):
    sample = tmp_path / "sample.json"
    sample.write_text("{}")
    execute = fake_execute({"SELECT 1": QueryResult(rows=[(1,)]), "SELECT 2": QueryResult(rows=[(2,), (3,)])})
    run_dir = runner.run_eval(
        GoldOracle(), QUESTIONS, GOLD, prices=PRICES, sample_path=sample, runs_dir=tmp_path, execute=execute
    )
    cfg = json.loads((run_dir / "config.json").read_text())
    assert cfg["question_ids"] == [1, 2]
    assert cfg["prices_per_million_tokens"] == PRICES
    assert cfg["sample"] == "sample.json"
    assert len(cfg["sample_sha256"]) == 64
    assert set(cfg["git"]) == {"sha", "dirty"}


def test_git_state_when_git_unavailable(monkeypatch):
    def boom(*a, **k):
        raise subprocess.CalledProcessError(128, "git")

    monkeypatch.setattr(runner.subprocess, "run", boom)
    assert runner.git_state() == {"sha": None, "dirty": None}


def test_run_writes_summary(tmp_path):
    execute = fake_execute({"SELECT 1": QueryResult(rows=[(1,)]), "SELECT 2": QueryResult(rows=[(9,)])})
    run_dir = runner.run_eval(GoldOracle(), QUESTIONS, GOLD, runs_dir=tmp_path, execute=execute)
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["overall"] == {"n": 2, "correct": 1, "ex": 50.0}


def test_strategy_artifacts_are_saved_with_the_run(tmp_path):
    class WithArtifacts(GoldOracle):
        artifacts = {"schemas": {"db": "CREATE TABLE x (a int);"}}

    execute = fake_execute({"SELECT 1": QueryResult(rows=[(1,)]), "SELECT 2": QueryResult(rows=[(2,), (3,)])})
    with_artifacts = runner.run_eval(
        WithArtifacts(), QUESTIONS, GOLD, runs_dir=tmp_path / "a", execute=execute
    )
    without = runner.run_eval(GoldOracle(), QUESTIONS, GOLD, runs_dir=tmp_path / "b", execute=execute)
    assert json.loads((with_artifacts / "artifacts.json").read_text()) == WithArtifacts.artifacts
    assert not (without / "artifacts.json").exists()
