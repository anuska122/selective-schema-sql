import sys
from pathlib import Path

from sqlagent.eval.report import results_table


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: results_table.py runs/<run> [runs/<run> ...]")
        return 2
    print(results_table([Path(p) for p in sys.argv[1:]]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
