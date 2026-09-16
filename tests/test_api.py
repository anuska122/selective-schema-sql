import pytest
from fastapi.testclient import TestClient

from sqlagent.api import app as app_module
from sqlagent.api.service import AskService
from sqlagent.db import QueryResult
from sqlagent.eval.types import Prediction, StageTrace


class FakeStrategy:
    name = "fake"
    config: dict = {}

    def __init__(self, prediction):
        self.prediction = prediction
        self.questions = []

    def answer(self, question):
        self.questions.append(question)
        if isinstance(self.prediction, Exception):
            raise self.prediction
        return self.prediction


PREDICTION = Prediction(
    "SELECT colour FROM colour",
    [StageTrace("generate", 5.0, 1, "m", tokens_in=10, tokens_out=3)],
    {"selected": ["colour"], "rung": "generate"},
)


ROWS = QueryResult(columns=["colour"], rows=[("Blue",), (1,)])


def service(prediction=PREDICTION, result=ROWS):
    return AskService(FakeStrategy(prediction), execute=lambda sql, **kw: result)


def test_ask_returns_sql_rows_and_trace():
    answer = service().ask("what colours are there", db_id="superhero")
    assert answer["sql"] == "SELECT colour FROM colour"
    assert answer["columns"] == ["colour"]
    assert answer["rows"] == [["Blue"], ["1"]]
    assert answer["error"] is None
    assert answer["stages"][0]["name"] == "generate"
    assert answer["details"]["selected"] == ["colour"]


def test_ask_passes_the_database_to_the_strategy():
    svc = service()
    svc.ask("q", db_id="superhero")
    assert svc.strategy.questions[0].db_id == "superhero"


def test_ask_reports_execution_errors():
    answer = service(result=QueryResult(error="boom", error_type="db_error")).ask("q")
    assert answer["error"] == "db_error: boom"
    assert answer["rows"] == []


def test_ask_reports_missing_sql():
    answer = service(prediction=Prediction(None)).ask("q")
    assert answer["error"] == "no SQL produced"
    assert answer["sql"] is None


@pytest.fixture
def client():
    app_module.get_service.cache_clear()
    with TestClient(app_module.app) as client:
        yield client
    app_module.get_service.cache_clear()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ask_endpoint(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_service", lambda: service())
    response = client.post("/ask", json={"question": "what colours are there"})
    assert response.status_code == 200
    assert response.json()["sql"] == "SELECT colour FROM colour"


def test_ask_endpoint_rejects_empty_question(client):
    assert client.post("/ask", json={"question": ""}).status_code == 422


def test_ask_endpoint_reports_backend_failure(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_service", lambda: service(prediction=RuntimeError("model down")))
    response = client.post("/ask", json={"question": "q"})
    assert response.status_code == 502
    assert "model down" in response.json()["detail"]
