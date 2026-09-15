import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime

from sqlagent import db
from sqlagent.eval.dataset import DATASET, QUOTAS, SAMPLE, SEED, Question, load_questions, stratified_sample


def gold_unusable_reason(q: Question) -> str | None:
    result = db.execute(q.gold_sql, caller="make_sample", question_id=q.question_id)
    if not result.ok:
        return f"{result.error_type}: {result.error}"
    if result.truncated:
        return f"gold result exceeds {db.MAX_ROWS} rows"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the frozen stratified eval sample.")
    parser.add_argument("--force", action="store_true", help="overwrite an existing sample")
    args = parser.parse_args()
    if SAMPLE.exists() and not args.force:
        print(f"{SAMPLE.name} already exists and is frozen; use --force only before any baseline run")
        return 1

    questions, replaced = stratified_sample(load_questions(), QUOTAS, SEED, gold_unusable_reason)
    SAMPLE.write_text(
        json.dumps(
            {
                "created": datetime.now(UTC).date().isoformat(),
                "source": DATASET.name,
                "seed": SEED,
                "quotas": QUOTAS,
                "questions": [
                    {"question_id": q.question_id, "db_id": q.db_id, "difficulty": q.difficulty}
                    for q in questions
                ],
                "replaced": replaced,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"wrote {len(questions)} questions, {len(replaced)} replaced")
    print("by difficulty:", dict(Counter(q.difficulty for q in questions)))
    print("by database:", dict(sorted(Counter(q.db_id for q in questions).items())))
    for r in replaced:
        print("  replaced", r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
