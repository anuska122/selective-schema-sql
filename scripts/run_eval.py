import argparse
import sys

from sqlagent import llm
from sqlagent.eval.dataset import SAMPLE, load_sample
from sqlagent.eval.gold import load_gold
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
    args = parser.parse_args()

    questions = load_sample()
    if args.qids:
        wanted = {int(q) for q in args.qids.split(",")}
        questions = [q for q in questions if q.question_id in wanted]
    questions = questions[: args.limit]
    run_dir = run_eval(
        STRATEGIES[args.strategy](),
        questions,
        load_gold(questions),
        prices=llm.PRICES,
        sample_path=SAMPLE if args.limit is None and not args.qids else None,
    )
    print(run_dir.name)
    print((run_dir / "summary.json").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
