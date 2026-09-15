import argparse
import json
import sys

from sqlagent.eval.dataset import SAMPLE, load_sample
from sqlagent.eval.gold import load_gold
from sqlagent.eval.runner import run_eval
from sqlagent.strategies.oracle import GoldOracle

STRATEGIES = {"gold_oracle": GoldOracle}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a strategy over the frozen sample.")
    parser.add_argument("strategy", choices=sorted(STRATEGIES))
    args = parser.parse_args()

    questions = load_sample()
    run_dir = run_eval(STRATEGIES[args.strategy](), questions, load_gold(questions), sample_path=SAMPLE)
    rows = [json.loads(line) for line in (run_dir / "results.jsonl").read_text().splitlines()]
    correct = sum(r["correct"] for r in rows)
    print(f"{run_dir.name}: EX {correct}/{len(rows)} = {100 * correct / len(rows):.1f}%")
    for r in rows:
        if not r["correct"]:
            print(f"  wrong qid={r['qid']} {r['exec_error'] or 'result mismatch'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
