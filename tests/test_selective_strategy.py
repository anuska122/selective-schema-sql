from sqlagent.eval.dataset import Question
from sqlagent.eval.types import StageTrace
from sqlagent.index.fk_graph import FKGraph, ForeignKey
from sqlagent.llm import LLMResponse
from sqlagent.retrieval.retriever import TableCandidate
from sqlagent.selection.selector import Selector
from sqlagent.strategies.selective import Selective

RENDERS = {
    "account": "CREATE TABLE account (account_id bigint);",
    "client": "CREATE TABLE client (client_id bigint);",
    "disp": "CREATE TABLE disp (account_id bigint, client_id bigint);",
}
GRAPH = FKGraph(
    [
        ForeignKey("a", "disp", ("account_id",), "account", ("account_id",)),
        ForeignKey("b", "disp", ("client_id",), "client", ("client_id",)),
    ]
)
QUESTION = Question(1, "financial", "who owns which account", "", "SELECT 1", "simple")


class FakeRetriever:
    def __init__(self):
        self.calls = []

    def retrieve(self, question, limit=30, db_id=None):
        self.calls.append((question, limit, db_id))
        return [TableCandidate(t, "financial", 0.5) for t in ("account", "client")]


class FakeClient:
    def __init__(self, select_text, sql_text):
        self.responses = [select_text, sql_text]
        self.calls = []

    def complete(self, messages, **kw):
        self.calls.append((messages, kw))
        text = self.responses.pop(0)
        return LLMResponse(text, StageTrace(kw["stage"], 2.0, 1, kw["model"], tokens_in=50, tokens_out=10))


def build(select_text='{"tables": ["account", "client"]}', sql_text="SELECT 1", layout="standard"):
    client = FakeClient(select_text, sql_text)
    retriever = FakeRetriever()
    return Selective(client, retriever, Selector(client, GRAPH), RENDERS, layout=layout), client, retriever


def test_prompt_contains_only_selected_and_bridge_tables():
    strategy, client, _ = build()
    prediction = strategy.answer(QUESTION)

    assert prediction.sql == "SELECT 1"
    generate_prompt = client.calls[1][0][1]["content"]
    assert "CREATE TABLE disp" in generate_prompt
    assert generate_prompt.count("CREATE TABLE") == 3
    assert [s.name for s in prediction.stages] == ["retrieve", "select", "generate"]
    assert sum(s.llm_calls for s in prediction.stages) == 2


def test_standard_layout_filters_by_database_pooled_does_not():
    _, _, standard = build(layout="standard")
    strategy, _, retriever = build(layout="pooled")
    strategy.answer(QUESTION)
    assert retriever.calls[0][2] is None

    strategy, _, retriever = build(layout="standard")
    strategy.answer(QUESTION)
    assert retriever.calls[0][2] == "financial"


def test_falls_back_to_top_candidates_when_selection_is_empty():
    strategy, client, _ = build(select_text='{"tables": []}')
    strategy.answer(QUESTION)
    generate_prompt = client.calls[1][0][1]["content"]
    assert "CREATE TABLE account" in generate_prompt
    assert "CREATE TABLE client" in generate_prompt


def test_config_records_both_models_and_layout():
    strategy, _, _ = build(layout="pooled")
    assert strategy.config["model"] == "openai/gpt-oss-120b"
    assert strategy.config["selector_model"] == "openai/gpt-oss-20b"
    assert strategy.config["layout"] == "pooled"
    assert len(strategy.config["schema_sha256"]) == 64


def test_selector_failure_falls_back_to_top_candidates():
    strategy, client, _ = build(select_text="not json")
    prediction = strategy.answer(QUESTION)
    assert prediction.sql == "SELECT 1"
    assert [s.name for s in prediction.stages] == ["retrieve", "select_failed", "generate"]
    generate_prompt = client.calls[1][0][1]["content"]
    assert "CREATE TABLE account" in generate_prompt
