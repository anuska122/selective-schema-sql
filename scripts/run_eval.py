import argparse
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
    print(run_dir.name)
    print((run_dir / "summary.json").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
