import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlagent import config, db, llm, schema
from sqlagent.index import embeddings as emb
from sqlagent.index.descriptions import DescriptionStore
from sqlagent.index.fk_graph import FKGraph, load_foreign_keys
from sqlagent.index.infer_keys import Column, infer_foreign_keys
from sqlagent.index.values import ValueIndex, build_value_index

INDEX_DIR = config.ROOT / "data" / "index"
TABLE_MAP = config.ROOT / "eval" / "table_db_map.json"


def load_columns(execute: Callable[..., db.QueryResult]) -> list[Column]:
    result = execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position",
        caller="index",
        question_id=None,
    )
    if not result.ok:
        raise RuntimeError(f"column introspection failed: {result.error}")
    return [Column(*row) for row in result.rows]


def load_reserved(execute: Callable[..., db.QueryResult]) -> set[str]:
    result = execute(
        "SELECT word FROM pg_get_keywords() WHERE catcode IN ('R', 'T')", caller="index", question_id=None
    )
    if not result.ok:
        raise RuntimeError(f"keyword lookup failed: {result.error}")
    return {row[0] for row in result.rows}


def build(
    index_dir: Path = INDEX_DIR,
    table_map: Path = TABLE_MAP,
    execute: Callable[..., db.QueryResult] = db.execute,
    embedder: emb.Embedder | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    databases = json.loads(table_map.read_text())["databases"]
    columns = load_columns(execute)
    reserved = load_reserved(execute)

    declared = load_foreign_keys(execute)
    inferred, candidates = infer_foreign_keys(columns, list(databases.values()), declared, reserved, execute)
    graph = FKGraph(declared + inferred, [c.table for c in columns])
    graph.save(index_dir / "fk_graph.json")
    log(
        f"foreign keys: {len(declared)} declared + {len(inferred)} inferred (of {len(candidates)} candidates)"
    )

    value_index, value_report = build_value_index(reserved, execute)
    value_index.save(index_dir / "values.json")
    log(f"values: {value_report['values']} in {value_report['indexed_columns']} columns")

    store = DescriptionStore(index_dir / "descriptions.json")
    described = set(store.tables)
    missing = sorted({c.table for c in columns} - described)
    if missing:
        raise RuntimeError(
            f"{len(missing)} tables have no description (run scripts/describe_schema.py): {missing[:5]}"
        )
    log(f"descriptions: {len(store.tables)} tables")

    column_types: dict[str, dict[str, str]] = {}
    for c in columns:
        column_types.setdefault(c.table, {})[c.name] = c.data_type
    documents = emb.build_documents(databases, store.tables, column_types)
    index = emb.SchemaIndex(embedder or emb.FastEmbedEmbedder(), path=index_dir / "chroma")
    index.rebuild(documents, progress=lambda done, total: log(f"embedding {done}/{total}"))
    log(f"embeddings: {len(documents)} documents")

    manifest = {
        "created": datetime.now(UTC).isoformat(),
        "tables": len({c.table for c in columns}),
        "columns": len(columns),
        "foreign_keys": {"declared": len(declared), "inferred": len(inferred), "candidates": len(candidates)},
        "fk_graph_sha256": graph.content_hash(),
        "values": value_report,
        "values_sha256": ValueIndex.load(index_dir / "values.json").content_hash(),
        "descriptions": store.totals(),
        "embeddings": index.manifest(documents),
        "offline_cost": {
            "llm_tokens_in": store.totals()["tokens_in"],
            "llm_tokens_out": store.totals()["tokens_out"],
            "list_price_usd": store.totals()["list_price_usd"],
            "models": sorted({d.model for d in store.tables.values()}),
            "prices_per_million_tokens": llm.PRICES,
        },
    }
    manifest["content_sha256"] = schema.sha256(
        json.dumps(
            [manifest["fk_graph_sha256"], manifest["values_sha256"], manifest["embeddings"]["sha256"]],
            sort_keys=True,
        )
    )
    (index_dir / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    return manifest
