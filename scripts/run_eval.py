import argparse
import json
import sys
from pathlib import Path

from sqlagent import db, llm
from sqlagent.eval.dataset import DATASET, SAMPLE, load_questions, load_sample
from sqlagent.eval.gold import GOLD_CACHE, load_gold
from sqlagent.eval.metrics import COMPARISONS
from sqlagent.eval.runner import run_eval
from sqlagent.strategies.full_schema import FullSchema
from sqlagent.strategies.oracle import GoldOracle
from sqlagent.strategies.selective import build_selective

STRATEGIES = {
    "gold_oracle": GoldOracle,
    "full_schema": lambda: FullSchema(llm.GroqClient()),
    "selective": build_selective,
    "selective_pooled": lambda: build_selective(layout="pooled"),
    "selective_validated": lambda: build_selective(validate=True),
    "selective_recall": lambda: build_selective(validate=True, recall_first=True),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a strategy over the frozen sample.")
    parser.add_argument("strategy", choices=sorted(STRATEGIES))
    parser.add_argument("--limit", type=int, help="only the first N questions (smoke test)")
    parser.add_argument("--qids", help="comma-separated question ids to run")
    parser.add_argument("--resume", type=Path, help="continue an incomplete run directory")
    parser.add_argument("--all", action="store_true", help="evaluate the full dataset")
    parser.add_argument("--gold-cache", type=Path, help="gold cache for the selected dataset")
    parser.add_argument("--comparison", choices=COMPARISONS, default="multiset")
    parser.add_argument("--max-rows", type=int, default=db.MAX_ROWS, help="evaluation-only row cap")
    args = parser.parse_args()
    if not 1 <= args.max_rows <= 1_000_000:
        parser.error("--max-rows must be between 1 and 1000000")

    questions = load_questions() if args.all else load_sample()
    gold_cache = args.gold_cache or (GOLD_CACHE.with_name("all.json") if args.all else GOLD_CACHE)
    metadata = gold_cache.with_suffix(".meta.json")
    cached_cap = json.loads(metadata.read_text())["max_rows"] if metadata.exists() else db.MAX_ROWS
    if cached_cap != args.max_rows:
        parser.error("gold cache row cap differs; use the same --max-rows as cache_gold.py")
    if args.qids:
        wanted = {int(q) for q in args.qids.split(",")}
        questions = [q for q in questions if q.question_id in wanted]
    questions = questions[: args.limit]
    run_dir = run_eval(
        STRATEGIES[args.strategy](),
        questions,
        load_gold(questions, path=gold_cache),
        prices=llm.PRICES,
        sample_path=(DATASET if args.all else SAMPLE),
        comparison=args.comparison,
        max_rows=args.max_rows,
        resume=args.resume,
    )
    print(run_dir.name)
    summary = (run_dir / "summary.json").read_text()
    print(summary)
    return 2 if json.loads(summary).get("incomplete") else 0


if __name__ == "__main__":
    sys.exit(main())
