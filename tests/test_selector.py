import pytest

from sqlagent.eval.types import StageTrace
from sqlagent.index.fk_graph import FKGraph, ForeignKey
from sqlagent.llm import LLMResponse
from sqlagent.retrieval.retriever import TableCandidate
from sqlagent.selection.selector import Selector, expand_for_joins, parse_tables, render_candidates

GRAPH = FKGraph(
    [
        ForeignKey("a", "disp", ("account_id",), "account", ("account_id",)),
        ForeignKey("b", "disp", ("client_id",), "client", ("client_id",)),
    ],
    ["loan"],
)
CANDIDATES = [
    TableCandidate("account", "financial", 0.9, ["account_id"], ["frequency=monthly"]),
    TableCandidate("client", "financial", 0.8, ["client_id"]),
    TableCandidate("loan", "financial", 0.2),
]


class FakeClient:
    def __init__(self, text):
        self.text, self.calls = text, []

    def complete(self, messages, **kw):
        self.calls.append((messages, kw))
        return LLMResponse(self.text, StageTrace("select", 3.0, 1, kw["model"], tokens_in=120, tokens_out=20))


def test_render_candidates_lists_columns_and_values():
    text = render_candidates(CANDIDATES)
    assert "- account | columns: account_id | matching values: frequency=monthly" in text
    assert text.splitlines()[-1] == "- loan"


def test_parse_tables_keeps_known_names_only():
    chosen, unknown = parse_tables('{"tables": ["Account", "account", "ghost"]}', ["account", "client"])
    assert chosen == ["account"]
    assert unknown == ["ghost"]


@pytest.mark.parametrize("text", ["not json", '{"tables": "account"}'])
def test_parse_tables_rejects_bad_output(text):
    with pytest.raises(ValueError):
        parse_tables(text, ["account"])


def test_expand_adds_bridge_tables():
    tables, added = expand_for_joins(["account", "client"], GRAPH)
    assert tables == ["account", "client", "disp"]
    assert added == ["disp"]


def test_expand_leaves_single_or_unconnectable_tables():
    assert expand_for_joins(["account"], GRAPH) == (["account"], [])
    assert expand_for_joins(["account", "loan"], GRAPH) == (["account", "loan"], [])


def test_selector_uses_cheap_model_and_expands_joins():
    client = FakeClient('{"tables": ["account", "client", "ghost"]}')
    selection = Selector(client, GRAPH).select("who owns which account", CANDIDATES)
    assert selection.chosen == ["account", "client"]
    assert selection.tables == ["account", "client", "disp"]
    assert selection.added_for_joins == ["disp"]
    assert selection.unknown == ["ghost"]
    assert selection.trace.llm_calls == 1
    _, kw = client.calls[0]
    assert kw["model"] == "openai/gpt-oss-20b"
    assert kw["json_mode"] is True
    assert kw["reasoning_effort"] == "low"
    assert kw["max_tokens"] == 1024


def test_render_candidates_adds_descriptions_when_given():
    text = render_candidates(CANDIDATES, {"account": "bank accounts", "loan": ""})
    assert (
        text.splitlines()[0]
        == "- account | bank accounts | columns: account_id | matching values: frequency=monthly"
    )
    assert text.splitlines()[2] == "- loan"


def test_selector_uses_the_configured_prompt_and_descriptions():
    from sqlagent.selection.selector import RECALL_FIRST_PROMPT

    client = FakeClient('{"tables": ["account"]}')
    Selector(
        client, GRAPH, descriptions={"account": "bank accounts"}, system_prompt=RECALL_FIRST_PROMPT
    ).select("q", CANDIDATES)
    messages, _ = client.calls[0]
    assert messages[0]["content"] == RECALL_FIRST_PROMPT
    assert "bank accounts" in messages[1]["content"]
