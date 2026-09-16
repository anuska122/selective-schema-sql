import hashlib
import json
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sqlagent import config, db
from sqlagent.eval.dataset import Question
from sqlagent.eval.gold import GoldResult
from sqlagent.eval.metrics import execution_match, stage_cost_usd
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
) -> dict:
    start = time.perf_counter()
    try:
        prediction = strategy.answer(question)
        strategy_error = None
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
    }
    if prediction.sql is None:
        row["exec_error"] = row["exec_error"] or "no_sql"
        return row

    result = execute(prediction.sql, caller=strategy.name, question_id=question.question_id)
    row["rows_returned"] = len(result.rows)
    row["truncated"] = result.truncated
    row["exec_ms"] = result.duration_ms
    if not result.ok:
        row["exec_error"] = f"{result.error_type}: {result.error}"
    else:
        row["correct"] = not result.truncated and execution_match(result.rows, gold.rows)
    return row


def run_eval(
    strategy: Strategy,
    questions: list[Question],
    gold: dict[int, GoldResult],
    *,
    prices: dict[str, dict[str, float]] | None = None,
    sample_path: Path | None = None,
    runs_dir: Path = RUNS_DIR,
    execute: Callable[..., db.QueryResult] = db.execute,
) -> Path:
    prices = prices or {}
    started = datetime.now(UTC)
    run_dir = runs_dir / f"{started.strftime('%Y%m%dT%H%M%SZ')}_{strategy.name}"
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "config.json").write_text(
        json.dumps(
            {
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
                "max_rows": db.MAX_ROWS,
                "statement_timeout_ms": db.STATEMENT_TIMEOUT_MS,
            },
            indent=2,
        )
        + "\n"
    )
    artifacts = getattr(strategy, "artifacts", None)
    if artifacts:
        (run_dir / "artifacts.json").write_text(json.dumps(artifacts, indent=1, sort_keys=True) + "\n")
    with (run_dir / "results.jsonl").open("w") as out:
        for q in questions:
            row = evaluate_question(strategy, q, gold[q.question_id], prices, execute)
            out.write(json.dumps(row, default=str) + "\n")
            out.flush()
    summarize(run_dir)
    return run_dir
