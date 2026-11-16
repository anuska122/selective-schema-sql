"""Attribute observed failures to pipeline stages using diagnostic heuristics."""

import argparse
import json
from collections import Counter
from pathlib import Path

from sqlagent.eval.dataset import load_questions
from sqlagent.eval.report import load_results
from sqlagent.index.build import TABLE_MAP
from sqlagent.validation.validator import referenced_names


def classify(row: dict, required: set[str]) -> str:
    if row["correct"]:
        return "correct"
    details = row.get("details", {})
    error = row.get("exec_error") or ""
    if error.startswith("strategy_error"):
        return "strategy_error"
    if required and "retrieved" in details and not required <= set(details["retrieved"]):
        return "retrieval_miss"
    selected = details.get("widened", details.get("selected"))
    if required and selected is not None and not required <= set(selected):
        return "selection_miss"
    if not row.get("pred_sql"):
        return "no_valid_sql"
    if error:
        return "execution_error"
    return "wrong_result"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    summary = json.loads((args.run / "summary.json").read_text())
    if summary.get("incomplete"):
        parser.error("run is incomplete; resume it before attributing model errors")
    known = json.loads(TABLE_MAP.read_text())["table_to_db"]
    questions = {q.question_id: q for q in load_questions()}
    buckets = {}
    for row in load_results(args.run):
        required = referenced_names(questions[row["qid"]].gold_sql)[0] & known.keys()
        buckets[row["qid"]] = classify(row, required)
    print(
        json.dumps(
            {
                "diagnostic_heuristics": True,
                "counts": dict(Counter(buckets.values())),
                "question_categories": buckets,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
