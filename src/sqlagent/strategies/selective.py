import json
import time
from pathlib import Path

from sqlagent import generation, llm, schema
from sqlagent.eval.dataset import Question
from sqlagent.eval.types import Prediction, StageTrace
from sqlagent.index.build import INDEX_DIR, TABLE_MAP
from sqlagent.index.fk_graph import FKGraph
from sqlagent.retrieval.loading import load_retriever
from sqlagent.retrieval.retriever import Retriever
from sqlagent.selection.selector import Selector

CANDIDATES = 30


def render_per_table(
    table_names: list[str], sample_rows: int = schema.SAMPLE_ROWS, execute=None
) -> dict[str, str]:
    kwargs = {"execute": execute} if execute else {}
    tables, reserved = schema.load_tables(sorted(table_names), sample_rows=sample_rows, **kwargs)
    return {t.name: schema.render_table(t, reserved) for t in tables}


class Selective:
    name = "selective"

    def __init__(
        self,
        client: llm.GroqClient,
        retriever: Retriever,
        selector: Selector,
        table_renders: dict[str, str],
        *,
        layout: str = "standard",
        candidates: int = CANDIDATES,
        model: str = llm.GENERATOR_MODEL,
        reasoning_effort: str = llm.REASONING_EFFORT,
    ):
        self.client = client
        self.retriever = retriever
        self.selector = selector
        self.table_renders = table_renders
        self.layout = layout
        self.candidates = candidates
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.config = {
            "model": model,
            "selector_model": selector.model,
            "reasoning_effort": reasoning_effort,
            "temperature": 0,
            "layout": layout,
            "candidates": candidates,
            "schema_format": "ddl_with_keys",
            "evidence": False,
            "prompt_sha256": schema.sha256(generation.SYSTEM_PROMPT + generation.USER_TEMPLATE),
            "schema_sha256": schema.sha256(json.dumps(table_renders, sort_keys=True)),
        }

    def answer(self, question: Question) -> Prediction:
        start = time.perf_counter()
        db_id = question.db_id if self.layout == "standard" else None
        candidates = self.retriever.retrieve(question.question, limit=self.candidates, db_id=db_id)
        retrieve_trace = StageTrace("retrieve", round((time.perf_counter() - start) * 1000, 2))

        selection = self.selector.select(question.question, candidates)
        tables = [t for t in selection.tables if t in self.table_renders]
        if not tables:
            tables = [c.table for c in candidates[:5] if c.table in self.table_renders]

        schema_text = "\n\n".join(self.table_renders[t] for t in tables)
        sql, generate_trace = generation.generate_sql(
            self.client, schema_text, question.question, self.model, self.reasoning_effort
        )
        return Prediction(sql=sql, stages=[retrieve_trace, selection.trace, generate_trace])


def build_selective(
    client: llm.GroqClient | None = None,
    *,
    layout: str = "standard",
    index_dir: Path = INDEX_DIR,
    table_map: Path = TABLE_MAP,
) -> Selective:
    client = client or llm.GroqClient()
    table_names = list(json.loads(table_map.read_text())["table_to_db"])
    graph = FKGraph.load(index_dir / "fk_graph.json")
    return Selective(
        client,
        load_retriever(index_dir=index_dir, table_map=table_map),
        Selector(client, graph),
        render_per_table(table_names),
        layout=layout,
    )
