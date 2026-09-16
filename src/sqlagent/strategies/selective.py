import json
import time
from pathlib import Path

from sqlagent import generation, llm, schema
from sqlagent.eval.dataset import Question
from sqlagent.eval.types import Prediction, StageTrace
from sqlagent.index.build import INDEX_DIR, TABLE_MAP
from sqlagent.index.fk_graph import FKGraph
from sqlagent.retrieval.loading import load_retriever
from sqlagent.retrieval.retriever import Retriever, TableCandidate
from sqlagent.selection.selector import Selector
from sqlagent.validation.validator import Validation, Validator

CANDIDATES = 30
FALLBACK_TABLES = 5
WIDEN_TABLES = 12


def render_per_table(
    table_names: list[str], sample_rows: int = schema.SAMPLE_ROWS, execute=None
) -> dict[str, str]:
    kwargs = {"execute": execute} if execute else {}
    tables, reserved = schema.load_tables(sorted(table_names), sample_rows=sample_rows, **kwargs)
    return {t.name: schema.render_table(t, reserved) for t in tables}


def catalog_from_renders(table_names: list[str], execute=None) -> dict[str, set[str]]:
    kwargs = {"execute": execute} if execute else {}
    tables, _ = schema.load_tables(sorted(table_names), sample_rows=0, **kwargs)
    return {t.name: {c for c, _ in t.columns} for t in tables}


class Selective:
    name = "selective"

    def __init__(
        self,
        client: llm.GroqClient,
        retriever: Retriever,
        selector: Selector,
        table_renders: dict[str, str],
        validator: Validator | None = None,
        *,
        layout: str = "standard",
        candidates: int = CANDIDATES,
        fallback_tables: int = FALLBACK_TABLES,
        widen_tables: int = WIDEN_TABLES,
        model: str = llm.GENERATOR_MODEL,
        reasoning_effort: str = llm.REASONING_EFFORT,
    ):
        self.client = client
        self.retriever = retriever
        self.selector = selector
        self.table_renders = table_renders
        self.validator = validator
        self.layout = layout
        self.candidates = candidates
        self.fallback_tables = fallback_tables
        self.widen_tables = widen_tables
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.config = {
            "model": model,
            "selector_model": selector.model,
            "reasoning_effort": reasoning_effort,
            "temperature": 0,
            "layout": layout,
            "candidates": candidates,
            "fallback_tables": fallback_tables,
            "validation": validator is not None,
            "widen_tables": widen_tables if validator else None,
            "schema_format": "ddl_with_keys",
            "evidence": False,
            "prompt_sha256": schema.sha256(generation.SYSTEM_PROMPT + generation.USER_TEMPLATE),
            "schema_sha256": schema.sha256(json.dumps(table_renders, sort_keys=True)),
        }

    @property
    def validated_name(self) -> str:
        return f"{self.name}_validated" if self.validator else self.name

    def _select_tables(
        self, question: Question, candidates: list[TableCandidate], stages: list[StageTrace]
    ) -> list[str]:
        start = time.perf_counter()
        try:
            selection = self.selector.select(question.question, candidates)
            stages.append(selection.trace)
            tables = [t for t in selection.tables if t in self.table_renders]
        except (ValueError, llm.LLMError):
            stages.append(StageTrace("select_failed", round((time.perf_counter() - start) * 1000, 2)))
            tables = []
        if not tables:
            tables = [c.table for c in candidates[: self.fallback_tables] if c.table in self.table_renders]
        return tables

    def _render(self, tables: list[str]) -> str:
        return "\n\n".join(self.table_renders[t] for t in tables)

    def _check(self, sql: str | None, question: Question) -> Validation | None:
        return self.validator.validate(sql, question_id=question.question_id) if self.validator else None

    def answer(self, question: Question) -> Prediction:
        start = time.perf_counter()
        stages: list[StageTrace] = []
        db_id = question.db_id if self.layout == "standard" else None
        candidates = self.retriever.retrieve(question.question, limit=self.candidates, db_id=db_id)
        stages.append(StageTrace("retrieve", round((time.perf_counter() - start) * 1000, 2)))

        tables = self._select_tables(question, candidates, stages)
        details: dict = {
            "candidates": [c.table for c in candidates[:10]],
            "selected": tables,
            "rung": "generate",
        }

        sql, trace = generation.generate_sql(
            self.client, self._render(tables), question.question, self.model, self.reasoning_effort
        )
        stages.append(trace)
        check = self._check(sql, question)
        if check is None or check.ok:
            details["validation"] = check.stage if check else None
            return Prediction(sql=sql, stages=stages, details=details)

        details["first_error"] = check.message
        sql, trace = generation.repair_sql(
            self.client,
            self._render(tables),
            question.question,
            sql,
            check.message,
            self.model,
            self.reasoning_effort,
        )
        stages.append(trace)
        details["rung"] = "repair"
        check = self._check(sql, question)
        if check.ok:
            details["validation"] = "ok"
            return Prediction(sql=sql, stages=stages, details=details)

        widened = sorted(
            {*tables, *[c.table for c in candidates[: self.widen_tables] if c.table in self.table_renders]}
        )
        details.update(rung="widen", widened=widened, repair_error=check.message)
        sql, trace = generation.generate_sql(
            self.client, self._render(widened), question.question, self.model, self.reasoning_effort
        )
        stages.append(trace)
        final = self._check(sql, question)
        details["validation"] = final.stage if final else None
        return Prediction(sql=sql, stages=stages, details=details)


def build_selective(
    client: llm.GroqClient | None = None,
    *,
    layout: str = "standard",
    validate: bool = False,
    index_dir: Path = INDEX_DIR,
    table_map: Path = TABLE_MAP,
) -> Selective:
    client = client or llm.GroqClient()
    table_names = list(json.loads(table_map.read_text())["table_to_db"])
    graph = FKGraph.load(index_dir / "fk_graph.json")
    strategy = Selective(
        client,
        load_retriever(index_dir=index_dir, table_map=table_map),
        Selector(client, graph),
        render_per_table(table_names),
        Validator(catalog_from_renders(table_names)) if validate else None,
        layout=layout,
    )
    strategy.name = strategy.validated_name
    return strategy
