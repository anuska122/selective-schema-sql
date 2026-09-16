import json
from pathlib import Path

from sqlagent import config, generation, llm, schema
from sqlagent.eval.dataset import Question
from sqlagent.eval.types import Prediction

TABLE_MAP = config.ROOT / "eval" / "table_db_map.json"


class FullSchema:
    name = "full_schema"

    def __init__(
        self,
        client: llm.GroqClient,
        *,
        model: str = llm.GENERATOR_MODEL,
        reasoning_effort: str = llm.REASONING_EFFORT,
        sample_rows: int = schema.SAMPLE_ROWS,
        table_map: Path = TABLE_MAP,
        execute=None,
    ):
        self.client = client
        self.model = model
        self.reasoning_effort = reasoning_effort
        databases = json.loads(table_map.read_text())["databases"]
        kwargs = {"execute": execute} if execute else {}
        self.schemas: dict[str, str] = {}
        for db_id, tables in sorted(databases.items()):
            loaded, reserved = schema.load_tables(sorted(tables), sample_rows=sample_rows, **kwargs)
            self.schemas[db_id] = schema.render_schema(loaded, reserved)
        self.config = {
            "model": model,
            "reasoning_effort": reasoning_effort,
            "temperature": 0,
            "layout": "standard",
            "schema_format": "ddl_with_keys",
            "sample_rows": sample_rows,
            "evidence": False,
            "prompt_sha256": schema.sha256(generation.SYSTEM_PROMPT + generation.USER_TEMPLATE),
            "schema_sha256": schema.sha256(json.dumps(self.schemas, sort_keys=True)),
        }
        self.artifacts = {"schemas": self.schemas}

    def messages(self, question: Question) -> list[dict]:
        user = generation.USER_TEMPLATE.format(
            schema=self.schemas[question.db_id], question=question.question
        )
        return [{"role": "system", "content": generation.SYSTEM_PROMPT}, {"role": "user", "content": user}]

    def answer(self, question: Question) -> Prediction:
        sql, trace = generation.generate_sql(
            self.client, self.schemas[question.db_id], question.question, self.model, self.reasoning_effort
        )
        return Prediction(sql=sql, stages=[trace])
