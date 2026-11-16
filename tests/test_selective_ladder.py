import pytest

from sqlagent.db import QueryResult
from sqlagent.eval.dataset import Question
from sqlagent.eval.types import StageTrace
from sqlagent.index.fk_graph import FKGraph
from sqlagent.llm import LLMResponse
from sqlagent.retrieval.retriever import TableCandidate
from sqlagent.selection.selector import Selector
from sqlagent.strategies.selective import Selective
from sqlagent.validation.validator import Validator

RENDERS = {
    "account": "CREATE TABLE account (account_id bigint, frequency text);",
    "loan": "CREATE TABLE loan (loan_id bigint, amount bigint);",
    "card": "CREATE TABLE card (card_id bigint);",
}
CATALOG = {"account": {"account_id", "frequency"}, "loan": {"loan_id", "amount"}, "card": {"card_id"}}
QUESTION = Question(1, "financial", "how many accounts", "", "SELECT 1", "simple")


class FakeRetriever:
    def retrieve(self, question, limit=30, db_id=None):
        return [TableCandidate(t, "financial", 1.0) for t in ("account", "loan", "card")]


class ScriptedClient:
    def __init__(self, *texts):
        self.texts = list(texts)
        self.stages = []

    def complete(self, messages, **kw):
        self.stages.append(kw["stage"])
        text = self.texts.pop(0)
        return LLMResponse(text, StageTrace(kw["stage"], 1.0, 1, kw["model"], tokens_in=10, tokens_out=5))


def build(*texts, explain=lambda sql, **kw: QueryResult(rows=[])):
    client = ScriptedClient('{"tables": ["account"]}', *texts)
    strategy = Selective(
        client, FakeRetriever(), Selector(client, FKGraph([])), RENDERS, Validator(CATALOG, explain=explain)
    )
    return strategy, client


def test_valid_sql_skips_the_repair_call():
    strategy, client = build("SELECT count(*) FROM account")
    prediction = strategy.answer(QUESTION)
    assert client.stages == ["select", "generate"]
    assert prediction.details["rung"] == "generate"
    assert prediction.details["selected"] == ["account"]
    assert prediction.details["validation"] == "ok"


def test_bad_column_triggers_one_repair_call():
    strategy, client = build("SELECT ghost FROM account", "SELECT frequency FROM account")
    prediction = strategy.answer(QUESTION)
    assert client.stages == ["select", "generate", "repair"]
    assert prediction.sql == "SELECT frequency FROM account"
    assert prediction.details["rung"] == "repair"
    assert "unknown column: ghost" in prediction.details["first_error"]


def test_second_failure_widens_the_schema_and_regenerates():
    strategy, client = build(
        "SELECT ghost FROM account", "SELECT ghost2 FROM account", "SELECT amount FROM loan"
    )
    prediction = strategy.answer(QUESTION)
    assert client.stages == ["select", "generate", "repair", "generate"]
    assert prediction.details["rung"] == "widen"
    assert prediction.details["widened"] == ["account", "card", "loan"]
    assert prediction.sql == "SELECT amount FROM loan"


def test_explain_errors_also_drive_the_ladder():
    def explain(sql, **kw):
        if "DISTINCT" in sql:
            return QueryResult(error="ORDER BY expressions must appear in select list", error_type="db_error")
        return QueryResult(rows=[])

    strategy, client = build(
        "SELECT DISTINCT frequency FROM account", "SELECT frequency FROM account", explain=explain
    )
    prediction = strategy.answer(QUESTION)
    assert client.stages == ["select", "generate", "repair"]
    assert prediction.sql == "SELECT frequency FROM account"


def test_without_a_validator_nothing_is_checked_or_repaired():
    client = ScriptedClient('{"tables": ["account"]}', "SELECT ghost FROM account")
    strategy = Selective(client, FakeRetriever(), Selector(client, FKGraph([])), RENDERS, None)
    prediction = strategy.answer(QUESTION)
    assert client.stages == ["select", "generate"]
    assert prediction.sql == "SELECT ghost FROM account"
    assert prediction.details["validation"] is None
    assert strategy.validated_name == "selective"


@pytest.mark.parametrize("validate", [True, False])
def test_config_records_whether_validation_is_on(validate):
    client = ScriptedClient('{"tables": ["account"]}')
    validator = Validator(CATALOG) if validate else None
    strategy = Selective(client, FakeRetriever(), Selector(client, FKGraph([])), RENDERS, validator)
    assert strategy.config["validation"] is validate
    assert strategy.validated_name == ("selective_validated" if validate else "selective")


def test_failed_widening_does_not_return_invalid_sql_for_execution():
    strategy, client = build("SELECT ghost FROM account", "SELECT ghost2 FROM account", "DELETE FROM account")
    prediction = strategy.answer(QUESTION)
    assert prediction.sql is None
    assert prediction.details["validation"] == "parse"
    assert prediction.details["final_error"]
    assert client.stages == ["select", "generate", "repair", "generate"]
