from dataclasses import asdict
from typing import Any

from sqlagent import db
from sqlagent.eval.dataset import Question
from sqlagent.eval.types import Strategy

MAX_ROWS = 100


class AskService:
    def __init__(self, strategy: Strategy, execute=db.execute, max_rows: int = MAX_ROWS):
        self.strategy = strategy
        self.execute = execute
        self.max_rows = max_rows

    def ask(self, question: str, db_id: str = "") -> dict[str, Any]:
        prediction = self.strategy.answer(Question(0, db_id, question, "", "", ""))
        answer: dict[str, Any] = {
            "question": question,
            "sql": prediction.sql,
            "columns": [],
            "rows": [],
            "truncated": False,
            "error": None,
            "stages": [asdict(s) for s in prediction.stages],
            "details": prediction.details,
        }
        if prediction.sql is None:
            answer["error"] = "no SQL produced"
            return answer

        result = self.execute(prediction.sql, caller="api", question_id=None, max_rows=self.max_rows)
        answer.update(
            columns=result.columns,
            rows=[[str(v) for v in row] for row in result.rows],
            truncated=result.truncated,
            error=None if result.ok else f"{result.error_type}: {result.error}",
        )
        return answer
