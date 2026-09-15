import sys

from sqlagent.eval.dataset import load_sample
from sqlagent.eval.gold import GOLD_CACHE, compute_gold, load_gold, save_gold


def main() -> int:
    questions = load_sample()
    results, failures = compute_gold(questions)
    if failures:
        print(f"FAILED: {len(failures)} gold queries unusable; cache not written")
        for f in failures:
            print("  " + f)
        return 1
    save_gold(results)
    load_gold(questions)
    durations = sorted(g.duration_ms for g in results.values())
    print(f"cached {len(results)} gold results -> {GOLD_CACHE}")
    print(f"gold runtime ms: median {durations[len(durations) // 2]}, max {durations[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
