import argparse
import sys
from pathlib import Path

from sqlagent.eval.report import compare, format_comparison


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-question diff of two eval runs.")
    parser.add_argument("run_a", type=Path)
    parser.add_argument("run_b", type=Path)
    args = parser.parse_args()
    print(format_comparison(compare(args.run_a, args.run_b)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
