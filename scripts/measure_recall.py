import argparse
import json
import sys
from collections import Counter

import sqlglot
from sqlglot import exp

from sqlagent.eval.dataset import load_questions
from sqlagent.index.build import TABLE_MAP
from sqlagent.retrieval.loading import load_retriever

KS = (10, 20, 30, 50)


def gold_tables(sql: str, known: dict[str, str]) -> set[str]:
    tree = sqlglot.parse_one(sql, read="postgres")
    return {t.name.lower() for t in tree.find_all(exp.Table) if t.name.lower() in known}


def main() -> int:
    parser = argparse.ArgumentParser(description="Table recall of the retriever on every question.")
    parser.add_argument("--layout", choices=["pooled", "standard"], default="pooled")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    known = json.loads(TABLE_MAP.read_text())["table_to_db"]
    retriever = load_retriever()
    questions = load_questions()[: args.limit]

    hits = Counter()
    full = Counter()
    misses = []
    scored = 0
    for q in questions:
        gold = gold_tables(q.gold_sql, known)
        if not gold:
            continue
        scored += 1
        found = [
            c.table
            for c in retriever.retrieve(
                q.question, limit=max(KS), db_id=None if args.layout == "pooled" else q.db_id
            )
        ]
        for k in KS:
            top = set(found[:k])
            hits[k] += len(gold & top)
            full[k] += gold <= top
        if not gold <= set(found[:30]):
            misses.append({"qid": q.question_id, "db_id": q.db_id, "missing": sorted(gold - set(found[:30]))})

    total_gold = sum(len(gold_tables(q.gold_sql, known)) for q in questions)
    print(f"layout={args.layout} questions={scored} gold tables={total_gold}")
    for k in KS:
        table_recall = 100 * hits[k] / total_gold
        complete = 100 * full[k] / scored
        print(f"  recall@{k:<3d} tables {table_recall:5.1f}%   all tables found {complete:5.1f}%")
    print(f"questions missing a table at 30: {len(misses)}")
    for m in misses[:15]:
        print("  ", m)
    return 0


if __name__ == "__main__":
    sys.exit(main())
