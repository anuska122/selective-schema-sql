import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlagent import config

DATASET = config.ROOT / "data" / "minidev" / "MINIDEV" / "mini_dev_postgresql.json"
SAMPLE = config.ROOT / "eval" / "sample_50.json"
QUOTAS = {"simple": 15, "moderate": 25, "challenging": 10}
SEED = 20260915


@dataclass(frozen=True)
class Question:
    question_id: int | str
    db_id: str
    question: str
    evidence: str
    gold_sql: str
    difficulty: str


def load_questions(path: Path = DATASET) -> list[Question]:
    by_id: dict[int, Question] = {}
    for raw in json.loads(path.read_text()):
        q = Question(
            question_id=raw["question_id"],
            db_id=raw["db_id"],
            question=raw["question"],
            evidence=raw["evidence"],
            gold_sql=raw["SQL"],
            difficulty=raw["difficulty"],
        )
        existing = by_id.setdefault(q.question_id, q)
        if existing != q:
            raise ValueError(f"question_id {q.question_id} appears twice with different content")
    return list(by_id.values())


def stratified_sample(
    questions: list[Question],
    quotas: dict[str, int],
    seed: int,
    unusable_reason: Callable[[Question], str | None],
) -> tuple[list[Question], list[dict]]:
    rng = random.Random(seed)  # noqa: S311
    chosen: list[Question] = []
    replaced: list[dict] = []
    for difficulty in sorted(quotas):
        pool = sorted((q for q in questions if q.difficulty == difficulty), key=lambda q: q.question_id)
        rng.shuffle(pool)
        taken = 0
        for q in pool:
            if taken == quotas[difficulty]:
                break
            reason = unusable_reason(q)
            if reason:
                replaced.append({"question_id": q.question_id, "difficulty": difficulty, "reason": reason})
                continue
            chosen.append(q)
            taken += 1
        if taken < quotas[difficulty]:
            raise ValueError(f"only {taken} usable {difficulty} questions, need {quotas[difficulty]}")
    return sorted(chosen, key=lambda q: q.question_id), replaced


def load_sample(path: Path = SAMPLE, dataset: Path = DATASET) -> list[Question]:
    ids = {q["question_id"] for q in json.loads(path.read_text())["questions"]}
    return [q for q in load_questions(dataset) if q.question_id in ids]
