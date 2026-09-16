import json
import math
from collections import Counter, defaultdict
from pathlib import Path


def load_results(run_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


def _ex(rows: list[dict]) -> dict:
    correct = sum(r["correct"] for r in rows)
    return {"n": len(rows), "correct": correct, "ex": round(100 * correct / len(rows), 2) if rows else None}


def stage_breakdown(rows: list[dict]) -> dict:
    stages: dict[str, dict] = {}
    for row in rows:
        for stage in row.get("stages", []):
            entry = stages.setdefault(
                stage["name"],
                {
                    "questions": 0,
                    "llm_calls": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "cached_tokens": 0,
                    "latencies": [],
                },
            )
            entry["questions"] += 1
            for key in ("llm_calls", "tokens_in", "tokens_out", "cached_tokens"):
                entry[key] += stage.get(key, 0)
            entry["latencies"].append(stage.get("latency_ms", 0.0))
    return {
        name: {
            **{k: v for k, v in entry.items() if k != "latencies"},
            "p50_latency_ms": percentile(entry["latencies"], 50),
        }
        for name, entry in sorted(stages.items())
    }


def ladder_breakdown(rows: list[dict]) -> dict:
    rungs = Counter(row["details"].get("rung") for row in rows if row.get("details", {}).get("rung"))
    if not rungs:
        return {}
    correct = Counter(
        row["details"]["rung"] for row in rows if row.get("details", {}).get("rung") and row["correct"]
    )
    return {rung: {"questions": n, "correct": correct[rung]} for rung, n in sorted(rungs.items())}


def summarize(run_dir: Path, incomplete: str | None = None, answered: int = 0, planned: int = 0) -> dict:
    rows = load_results(run_dir)
    config = json.loads((run_dir / "config.json").read_text())
    by_difficulty = defaultdict(list)
    for r in rows:
        by_difficulty[r["difficulty"]].append(r)
    n = len(rows) or 1
    latencies = [r["latency_ms"] for r in rows]
    totals = {k: sum(r[k] for r in rows) for k in ("llm_calls", "tokens_in", "tokens_out", "cached_tokens")}
    cost = sum(r["cost_usd"] for r in rows)
    summary = {
        "run": run_dir.name,
        "strategy": config["strategy"],
        "git_sha": config["git"]["sha"],
        "overall": _ex(rows),
        "by_difficulty": {d: _ex(by_difficulty[d]) for d in sorted(by_difficulty)},
        "errors": dict(Counter(r["exec_error"].split(":")[0] for r in rows if r["exec_error"]).most_common()),
        "totals": {**totals, "cost_usd": round(cost, 6)},
        "per_question": {
            **{k: round(v / n, 2) for k, v in totals.items()},
            "cost_usd": round(cost / n, 6),
        },
        "latency_ms": {"p50": percentile(latencies, 50), "p95": percentile(latencies, 95)},
        "stages": stage_breakdown(rows),
    }
    ladder = ladder_breakdown(rows)
    if ladder:
        summary["ladder"] = ladder
    if incomplete:
        summary["incomplete"] = {"reason": incomplete, "answered": answered, "planned": planned}
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def compare(run_a: Path, run_b: Path) -> dict:
    for run in (run_a, run_b):
        summary_path = run / "summary.json"
        if summary_path.exists() and json.loads(summary_path.read_text()).get("incomplete"):
            raise ValueError(f"{run.name} is incomplete; re-run it before comparing")
    a = {r["qid"]: r for r in load_results(run_a)}
    b = {r["qid"]: r for r in load_results(run_b)}
    if a.keys() != b.keys():
        raise ValueError("runs cover different questions; compare runs on the same frozen sample")
    fixed = sorted(q for q in a if not a[q]["correct"] and b[q]["correct"])
    broken = sorted(q for q in a if a[q]["correct"] and not b[q]["correct"])

    def mean(run, key):
        return sum(r[key] for r in run.values()) / len(run)

    return {
        "a": run_a.name,
        "b": run_b.name,
        "n": len(a),
        "ex_a": _ex(list(a.values()))["ex"],
        "ex_b": _ex(list(b.values()))["ex"],
        "fixed": fixed,
        "broken": broken,
        "mean_tokens_in": (round(mean(a, "tokens_in"), 2), round(mean(b, "tokens_in"), 2)),
        "mean_cost_usd": (round(mean(a, "cost_usd"), 6), round(mean(b, "cost_usd"), 6)),
        "p50_latency_ms": (
            percentile([r["latency_ms"] for r in a.values()], 50),
            percentile([r["latency_ms"] for r in b.values()], 50),
        ),
    }


def format_comparison(c: dict) -> str:
    lines = [
        f"A: {c['a']}",
        f"B: {c['b']}",
        f"EX: {c['ex_a']}% -> {c['ex_b']}% on {c['n']} questions",
        f"fixed  ({len(c['fixed'])}): {c['fixed']}",
        f"broken ({len(c['broken'])}): {c['broken']}",
        f"net: {len(c['fixed']) - len(c['broken']):+d} questions",
        f"mean input tokens: {c['mean_tokens_in'][0]} -> {c['mean_tokens_in'][1]}",
        f"mean cost USD: {c['mean_cost_usd'][0]} -> {c['mean_cost_usd'][1]}",
        f"p50 latency ms: {c['p50_latency_ms'][0]} -> {c['p50_latency_ms'][1]}",
    ]
    return "\n".join(lines)
