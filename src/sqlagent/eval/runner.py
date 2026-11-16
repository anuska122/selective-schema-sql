import hashlib
import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sqlagent import config, db
from sqlagent.errors import AbortRun
from sqlagent.eval.dataset import Question
from sqlagent.eval.gold import GoldResult
from sqlagent.eval.metrics import COMPARISONS, execution_match, stage_cost_usd
from sqlagent.eval.report import summarize
from sqlagent.eval.types import Prediction, Strategy

RUNS_DIR = config.ROOT / "runs"


def _git(*args: str) -> str:
    cmd = ["git", *args]
    return subprocess.run(cmd, cwd=config.ROOT, capture_output=True, text=True, check=True).stdout.strip()  # noqa: S603, S607


def git_state() -> dict[str, str | bool | None]:
    try:
        return {
            "sha": _git("rev-parse", "HEAD"),
            "dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"sha": None, "dirty": None}


def evaluate_question(
    strategy: Strategy,
    question: Question,
    gold: GoldResult,
    prices: dict[str, dict[str, float]],
    execute: Callable[..., db.QueryResult],
    comparison: str = "multiset",
    max_rows: int = db.MAX_ROWS,
) -> dict:
    start = time.perf_counter()
    try:
        prediction = strategy.answer(question)
        strategy_error = None
    except AbortRun:
        raise
    except Exception as e:
        prediction = Prediction(sql=None)
        strategy_error = f"strategy_error: {type(e).__name__}: {e}"
    wait_ms = sum(s.wait_ms for s in prediction.stages)
    latency_ms = round((time.perf_counter() - start) * 1000 - wait_ms, 2)

    row = {
        "qid": question.question_id,
        "db_id": question.db_id,
        "difficulty": question.difficulty,
        "pred_sql": prediction.sql,
        "exec_error": strategy_error,
        "correct": False,
        "rows_returned": 0,
        "truncated": False,
        "exec_ms": 0.0,
        "llm_calls": sum(s.llm_calls for s in prediction.stages),
        "tokens_in": sum(s.tokens_in for s in prediction.stages),
        "tokens_out": sum(s.tokens_out for s in prediction.stages),
        "cached_tokens": sum(s.cached_tokens for s in prediction.stages),
        "latency_ms": latency_ms,
        "rate_limit_wait_ms": round(wait_ms, 2),
        "cost_usd": sum(stage_cost_usd(s, prices) for s in prediction.stages),
        "stages": [asdict(s) for s in prediction.stages],
        "details": prediction.details,
    }
    if prediction.sql is None:
        row["exec_error"] = row["exec_error"] or "no_sql"
        return row

    limits = {"max_rows": max_rows} if max_rows != db.MAX_ROWS else {}
    result = execute(prediction.sql, caller=strategy.name, question_id=question.question_id, **limits)
    row["rows_returned"] = len(result.rows)
    row["truncated"] = result.truncated
    row["exec_ms"] = result.duration_ms
    if not result.ok:
        row["exec_error"] = f"{result.error_type}: {result.error}"
    else:
        row["correct"] = not result.truncated and execution_match(
            result.rows, gold.rows, comparison=comparison
        )
    return row


def _new_run(
    strategy: Strategy,
    questions: list[Question],
    prices,
    sample_path: Path | None,
    runs_dir: Path,
    comparison: str,
    max_rows: int,
) -> Path:
    started = datetime.now(UTC)
    run_dir = runs_dir / f"{started.strftime('%Y%m%dT%H%M%SZ')}_{strategy.name}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "config.json").write_text(
        json.dumps(
            {
                "comparison": comparison,
                "strategy": strategy.name,
                "strategy_config": strategy.config,
                "started": started.isoformat(),
                "git": git_state(),
                "sample": sample_path.name if sample_path else None,
                "sample_sha256": hashlib.sha256(sample_path.read_bytes()).hexdigest()
                if sample_path
                else None,
                "question_ids": [q.question_id for q in questions],
                "prices_per_million_tokens": prices,
                "max_rows": max_rows,
                "questions_sha256": hashlib.sha256(
                    json.dumps([asdict(q) for q in questions], sort_keys=True).encode()
                ).hexdigest(),
                "statement_timeout_ms": db.STATEMENT_TIMEOUT_MS,
            },
            indent=2,
        )
        + "\n"
    )
    artifacts = getattr(strategy, "artifacts", None)
    if artifacts:
        (run_dir / "artifacts.json").write_text(json.dumps(artifacts, indent=1, sort_keys=True) + "\n")
    return run_dir


def _check_resumable(
    run_dir: Path, strategy: Strategy, questions: list[Question], comparison: str, max_rows: int
) -> set[int]:
    config = json.loads((run_dir / "config.json").read_text())
    mismatches = [
        name
        for name, same in (
            ("comparison", config.get("comparison", "set") == comparison),
            ("row cap", config.get("max_rows", db.MAX_ROWS) == max_rows),
            (
                "question contents",
                not config.get("questions_sha256")
                or config["questions_sha256"]
                == hashlib.sha256(
                    json.dumps([asdict(q) for q in questions], sort_keys=True).encode()
                ).hexdigest(),
            ),
            ("strategy", config["strategy"] == strategy.name),
            ("strategy settings", config["strategy_config"] == strategy.config),
            ("questions", config["question_ids"] == [q.question_id for q in questions]),
        )
        if not same
    ]
    if mismatches:
        raise ValueError(f"cannot resume {run_dir.name}: {', '.join(mismatches)} differ from this run")
    results = run_dir / "results.jsonl"
    return (
        {json.loads(line)["qid"] for line in results.read_text().splitlines()} if results.exists() else set()
    )


def run_eval(
    strategy: Strategy,
    questions: list[Question],
    gold: dict[int, GoldResult],
    *,
    prices: dict[str, dict[str, float]] | None = None,
    sample_path: Path | None = None,
    runs_dir: Path = RUNS_DIR,
    execute: Callable[..., db.QueryResult] = db.execute,
    resume: Path | None = None,
    comparison: str = "multiset",
    max_rows: int = db.MAX_ROWS,
) -> Path:
    if comparison not in COMPARISONS:
        raise ValueError(f"unknown comparison: {comparison}")
    if not 1 <= max_rows <= 1_000_000:
        raise ValueError("max_rows must be between 1 and 1000000")
    prices = prices or {}
    if resume:
        run_dir, done = resume, _check_resumable(resume, strategy, questions, comparison, max_rows)
    else:
        run_dir, done = (
            _new_run(strategy, questions, prices, sample_path, runs_dir, comparison, max_rows),
            set(),
        )
    aborted = None
    with (run_dir / "results.jsonl").open("a") as out:
        for q in questions:
            if q.question_id in done:
                continue
            try:
                row = evaluate_question(
                    strategy, q, gold[q.question_id], prices, execute, comparison, max_rows
                )
            except AbortRun as e:
                aborted = str(e)
                break
            out.write(json.dumps(row, default=str) + "\n")
            out.flush()
            done.add(q.question_id)
    summarize(run_dir, incomplete=aborted, answered=len(done), planned=len(questions))
    return run_dir
