from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlagent.eval.dataset import Question


@dataclass(frozen=True)
class StageTrace:
    name: str
    latency_ms: float
    llm_calls: int = 0
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cached_tokens: int = 0


@dataclass(frozen=True)
class Prediction:
    sql: str | None
    stages: list[StageTrace] = field(default_factory=list)


class Strategy(Protocol):
    name: str
    config: dict[str, Any]

    def answer(self, question: Question) -> Prediction: ...
