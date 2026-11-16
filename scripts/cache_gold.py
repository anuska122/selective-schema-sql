import argparse
import json
import sys
from functools import partial
from pathlib import Path

from sqlagent import db
from sqlagent.eval.dataset import load_questions, load_sample
from sqlagent.eval.gold import GOLD_CACHE, compute_gold, load_gold, save_gold


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache reference results without model calls.")
    parser.add_argument("--all", action="store_true", help="cache the full dataset")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--max-rows", type=int, default=db.MAX_ROWS, help="evaluation-only row cap")
    args = parser.parse_args()
    if not 1 <= args.max_rows <= 1_000_000:
        parser.error("--max-rows must be between 1 and 1000000")
    questions = load_questions() if args.all else load_sample()
    output = args.output or (GOLD_CACHE.with_name("all.json") if args.all else GOLD_CACHE)
    kwargs = {"execute": partial(db.execute, max_rows=args.max_rows)} if args.max_rows != db.MAX_ROWS else {}
    results, failures = compute_gold(questions, **kwargs)
    if failures:
        print(f"FAILED: {len(failures)} gold queries unusable; cache not written")
        for f in failures:
            print("  " + f)
        return 1
    save_gold(results, path=output)
    load_gold(questions, path=output)
    output.with_suffix(".meta.json").write_text(json.dumps({"max_rows": args.max_rows}, indent=2) + "\n")
    durations = sorted(g.duration_ms for g in results.values())
    print(f"cached {len(results)} gold results -> {output}")
    print(f"gold runtime ms: median {durations[len(durations) // 2]}, max {durations[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
