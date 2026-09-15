import json

import pytest

from sqlagent.eval import dataset
from sqlagent.eval.dataset import Question, stratified_sample


def make_questions():
    qs = []
    for i in range(30):
        difficulty = ["simple", "moderate", "challenging"][i % 3]
        qs.append(Question(i, f"db{i % 4}", f"q{i}", "", f"SELECT {i}", difficulty))
    return qs


def always_usable(q):
    return None


QUOTAS = {"simple": 3, "moderate": 4, "challenging": 2}


def test_meets_quotas():
    chosen, replaced = stratified_sample(make_questions(), QUOTAS, 1, always_usable)
    counts = {d: sum(q.difficulty == d for q in chosen) for d in QUOTAS}
    assert counts == QUOTAS
    assert replaced == []


def test_same_seed_same_sample_regardless_of_input_order():
    qs = make_questions()
    a, _ = stratified_sample(qs, QUOTAS, 7, always_usable)
    b, _ = stratified_sample(list(reversed(qs)), QUOTAS, 7, always_usable)
    assert a == b


def test_different_seed_different_sample():
    qs = make_questions()
    a, _ = stratified_sample(qs, QUOTAS, 1, always_usable)
    b, _ = stratified_sample(qs, QUOTAS, 2, always_usable)
    assert a != b


def test_unusable_questions_are_replaced_and_logged():
    qs = make_questions()
    baseline, _ = stratified_sample(qs, QUOTAS, 3, always_usable)
    bad_id = baseline[0].question_id

    chosen, replaced = stratified_sample(
        qs, QUOTAS, 3, lambda q: "timeout" if q.question_id == bad_id else None
    )
    assert bad_id not in {q.question_id for q in chosen}
    assert replaced == [{"question_id": bad_id, "difficulty": baseline[0].difficulty, "reason": "timeout"}]
    assert len(chosen) == sum(QUOTAS.values())


def test_raises_when_not_enough_usable_questions():
    with pytest.raises(ValueError, match="usable"):
        stratified_sample(make_questions(), {"simple": 11}, 1, always_usable)


def raw_question(qid, sql="SELECT 1"):
    return {
        "question_id": qid,
        "db_id": "a",
        "question": "q",
        "evidence": "",
        "SQL": sql,
        "difficulty": "simple",
    }


def test_load_questions_drops_exact_duplicates(tmp_path):
    source = tmp_path / "questions.json"
    source.write_text(json.dumps([raw_question(1), raw_question(2), raw_question(1)]))
    assert [q.question_id for q in dataset.load_questions(source)] == [1, 2]


def test_load_questions_rejects_conflicting_duplicates(tmp_path):
    source = tmp_path / "questions.json"
    source.write_text(json.dumps([raw_question(1), raw_question(1, sql="SELECT 2")]))
    with pytest.raises(ValueError, match="different content"):
        dataset.load_questions(source)


def test_load_questions_and_sample(tmp_path):
    source = tmp_path / "questions.json"
    source.write_text(
        json.dumps(
            [
                {
                    "question_id": 1,
                    "db_id": "a",
                    "question": "q1",
                    "evidence": "e",
                    "SQL": "SELECT 1",
                    "difficulty": "simple",
                },
                {
                    "question_id": 2,
                    "db_id": "b",
                    "question": "q2",
                    "evidence": "",
                    "SQL": "SELECT 2",
                    "difficulty": "moderate",
                },
            ]
        )
    )
    sample = tmp_path / "sample.json"
    sample.write_text(json.dumps({"questions": [{"question_id": 2}]}))

    assert dataset.load_questions(source)[0].gold_sql == "SELECT 1"
    (only,) = dataset.load_sample(sample, source)
    assert only.question_id == 2
    assert only.db_id == "b"
