import json

import pytest

from sqlagent.eval.report import compare, format_comparison, percentile, summarize


def row(qid, correct, difficulty="simple", error=None, latency=10.0, tokens_in=0, cost=0.0):
    return {
        "qid": qid,
        "difficulty": difficulty,
        "correct": correct,
        "exec_error": error,
        "latency_ms": latency,
        "llm_calls": 1 if tokens_in else 0,
        "tokens_in": tokens_in,
        "tokens_out": tokens_in // 10,
        "cached_tokens": tokens_in // 2,
        "cost_usd": cost,
    }


def write_run(path, rows, strategy="s"):
    path.mkdir()
    (path / "config.json").write_text(json.dumps({"strategy": strategy, "git": {"sha": "abc"}}))
    (path / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


@pytest.mark.parametrize(
    ("values", "pct", "expected"),
    [
        ([], 50, None),
        ([5.0], 95, 5.0),
        ([1, 2, 3, 4], 50, 2),
        ([1, 2, 3, 4], 95, 4),
        (list(range(1, 101)), 95, 95),
    ],
)
def test_percentile_nearest_rank(values, pct, expected):
    assert percentile(values, pct) == expected


def test_summarize_writes_summary(tmp_path):
    run = write_run(
        tmp_path / "run",
        [
            row(1, True, "simple", latency=10, tokens_in=100, cost=0.01),
            row(2, False, "simple", error="timeout: slow", latency=30, tokens_in=300, cost=0.03),
            row(3, True, "challenging", latency=20),
            row(4, False, "challenging", error="db_error: bad column", latency=40),
        ],
    )
    s = summarize(run)
    assert s["overall"] == {"n": 4, "correct": 2, "ex": 50.0}
    assert s["by_difficulty"]["challenging"] == {"n": 2, "correct": 1, "ex": 50.0}
    assert s["errors"] == {"timeout": 1, "db_error": 1}
    assert s["totals"]["tokens_in"] == 400
    assert s["totals"]["cost_usd"] == pytest.approx(0.04)
    assert s["per_question"]["tokens_in"] == 100
    assert s["latency_ms"] == {"p50": 20, "p95": 40}
    assert json.loads((run / "summary.json").read_text()) == s


def test_compare_lists_fixed_and_broken(tmp_path):
    a = write_run(tmp_path / "a", [row(1, True), row(2, False), row(3, False), row(4, True, tokens_in=1000)])
    b = write_run(tmp_path / "b", [row(1, True), row(2, True), row(3, False), row(4, False, tokens_in=200)])
    c = compare(a, b)
    assert c["fixed"] == [2]
    assert c["broken"] == [4]
    assert (c["ex_a"], c["ex_b"]) == (50.0, 50.0)
    assert c["mean_tokens_in"] == (250.0, 50.0)
    text = format_comparison(c)
    assert "fixed  (1): [2]" in text
    assert "net: +0 questions" in text


def test_compare_refuses_different_question_sets(tmp_path):
    a = write_run(tmp_path / "a", [row(1, True)])
    b = write_run(tmp_path / "b", [row(2, True)])
    with pytest.raises(ValueError, match="different questions"):
        compare(a, b)


def test_compare_refuses_incomplete_runs(tmp_path):
    a = write_run(tmp_path / "a", [row(1, True)])
    b = write_run(tmp_path / "b", [row(1, True)])
    (b / "summary.json").write_text(
        json.dumps({"incomplete": {"reason": "quota", "answered": 1, "planned": 50}})
    )
    with pytest.raises(ValueError, match="incomplete"):
        compare(a, b)


def stage(name, **kw):
    return {"name": name, "latency_ms": kw.pop("latency_ms", 10.0), **kw}


def test_summary_breaks_down_stages_and_ladder(tmp_path):
    rows = [
        {
            **row(1, True),
            "stages": [stage("retrieve"), stage("generate", llm_calls=1, tokens_in=500)],
            "details": {"rung": "generate"},
        },
        {
            **row(2, False),
            "stages": [
                stage("retrieve", latency_ms=30.0),
                stage("generate", llm_calls=1, tokens_in=700),
                stage("repair", llm_calls=1, tokens_in=900),
            ],
            "details": {"rung": "repair"},
        },
    ]
    summary = summarize(write_run(tmp_path / "run", rows))
    assert summary["stages"]["generate"] == {
        "questions": 2,
        "llm_calls": 2,
        "tokens_in": 1200,
        "tokens_out": 0,
        "cached_tokens": 0,
        "p50_latency_ms": 10.0,
    }
    assert summary["stages"]["repair"]["questions"] == 1
    assert summary["stages"]["retrieve"]["p50_latency_ms"] == 10.0
    assert summary["ladder"] == {
        "generate": {"questions": 1, "correct": 1},
        "repair": {"questions": 1, "correct": 0},
    }


def test_summary_omits_the_ladder_when_no_strategy_reports_rungs(tmp_path):
    summary = summarize(write_run(tmp_path / "run", [row(1, True)]))
    assert "ladder" not in summary
    assert summary["stages"] == {}


def test_results_table_from_run_summaries(tmp_path):
    from sqlagent.eval.report import results_table

    def run(name, strategy, layout, ex, tokens, cost, p50, incomplete=None):
        d = tmp_path / name
        d.mkdir()
        (d / "config.json").write_text(json.dumps({"strategy_config": {"layout": layout}}))
        summary = {
            "strategy": strategy,
            "overall": {"ex": ex},
            "per_question": {"tokens_in": tokens, "cost_usd": cost},
            "latency_ms": {"p50": p50},
        }
        if incomplete:
            summary["incomplete"] = incomplete
        (d / "summary.json").write_text(json.dumps(summary))
        return d

    table = results_table(
        [
            run("a", "full_schema", "standard", 50.0, 2219.28, 0.000522, 1300.6),
            run("b", "selective_validated", "pooled", 48.0, 1500.1, 0.0004, 1800),
        ]
    )
    lines = table.splitlines()
    assert lines[2] == "| Full schema (baseline) | own database | 50% | 2,219 | $0.00052 | 1.3s |"
    assert lines[3] == "| Selective + validation | all 75 | 48% | 1,500 | $0.00040 | 1.8s |"

    with pytest.raises(ValueError, match="incomplete"):
        results_table([run("c", "selective", "standard", 10, 1, 0, 1, incomplete={"answered": 3})])
