import argparse
import json
import sys

import sqlglot
from sqlglot import exp

from sqlagent import llm
from sqlagent.eval.dataset import load_sample
from sqlagent.index.build import INDEX_DIR, TABLE_MAP
from sqlagent.index.descriptions import DescriptionStore
from sqlagent.index.fk_graph import FKGraph
from sqlagent.retrieval.loading import load_retriever
from sqlagent.selection import selector as sel

PROMPTS = {"default": sel.SYSTEM_PROMPT, "recall_first": sel.RECALL_FIRST_PROMPT}


def gold_tables(sql: str, known: set[str]) -> set[str]:
    return {t.name.lower() for t in sqlglot.parse_one(sql, read="postgres").find_all(exp.Table)} & known


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Selector recall on the frozen sample (retrieve + select only)."
    )
    parser.add_argument("--prompt", choices=sorted(PROMPTS), default="default")
    parser.add_argument("--descriptions", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--show-misses", action="store_true")
    args = parser.parse_args()

    known = set(json.loads(TABLE_MAP.read_text())["table_to_db"])
    descriptions = None
    if args.descriptions:
        descriptions = {
            t: d.description for t, d in DescriptionStore(INDEX_DIR / "descriptions.json").tables.items()
        }
    client = llm.GroqClient()
    retriever = load_retriever()
    selector = sel.Selector(
        client,
        FKGraph.load(INDEX_DIR / "fk_graph.json"),
        descriptions=descriptions,
        system_prompt=PROMPTS[args.prompt],
    )

    tops = (0, 1, 2, 3, 4, 5)
    kept_at = dict.fromkeys(tops, 0)
    tables_at = dict.fromkeys(tops, 0)
    kept = tokens = 0
    questions = load_sample()[: args.limit]
    for q in questions:
        gold = gold_tables(q.gold_sql, known)
        candidates = retriever.retrieve(q.question, limit=30, db_id=q.db_id)
        selection = selector.select(q.question, candidates)
        chosen = set(selection.tables)
        kept += gold <= chosen
        if args.show_misses and not gold <= chosen:
            ranks = {c.table: i for i, c in enumerate(candidates)}
            missing = {t: ranks.get(t) for t in sorted(gold - chosen)}
            print(f"  miss {q.question_id}: chose {sorted(chosen)} missing (retriever rank) {missing}")
            print(f"       {q.question[:100]}")
        for top in tops:
            union = chosen | {c.table for c in candidates[:top]}
            kept_at[top] += gold <= union
            tables_at[top] += len(union)
        tokens += selection.trace.tokens_in + selection.trace.tokens_out

    n = len(questions)

    def line(label: str, hits: int, tables: int) -> str:
        return f"  {label:24s} {hits}/{n} ({100 * hits / n:.0f}%)   mean tables {tables / n:.1f}"

    print(f"prompt={args.prompt} descriptions={args.descriptions} questions={n}")
    for top in tops:
        label = "selector only:" if top == 0 else f"+ retriever top {top}:"
        print(line(label, kept_at[top], tables_at[top]))
    print(f"  selector tokens per question: {tokens / n:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
