import argparse
import json
import sys

from sqlagent import config, llm, schema
from sqlagent.index.descriptions import DescriptionStore, describe_table

STORE = config.ROOT / "data" / "index" / "descriptions.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate table and column descriptions (resumable).")
    parser.add_argument("--limit", type=int, help="describe at most N tables this run")
    args = parser.parse_args()

    databases = json.loads((config.ROOT / "eval" / "table_db_map.json").read_text())["databases"]
    store = DescriptionStore(STORE)
    client = llm.GroqClient()
    done = failed = 0
    for db_id, table_names in sorted(databases.items()):
        names = sorted(table_names)
        tables, reserved = schema.load_tables(names)
        for table in tables:
            if store.is_current(table, reserved):
                continue
            if args.limit is not None and done >= args.limit:
                break
            others = [n for n in names if n != table.name]
            try:
                description = describe_table(client, db_id, table, others, reserved)
            except llm.QuotaExhausted as e:
                print(f"stopped, quota exhausted: {e}\nre-run later to resume")
                print(json.dumps(store.totals()))
                return 0
            except (ValueError, llm.LLMError) as e:
                failed += 1
                print(f"  {db_id}.{table.name}: failed ({str(e)[:200]})")
                continue
            store.put(description)
            done += 1
            gaps = f" missing={description.missing_columns}" if description.missing_columns else ""
            gaps += f" invented={description.invented_columns}" if description.invented_columns else ""
            print(f"  {db_id}.{table.name}: {len(description.columns)} columns{gaps}")
    print(f"described {done} tables, {failed} failed")
    print(json.dumps(store.totals()))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
