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
    app_module.get_guard.cache_clear()
    with TestClient(app_module.app) as client:
        yield client
    app_module.get_service.cache_clear()
    app_module.get_guard.cache_clear()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ask_endpoint(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_service", lambda: service())
    response = client.post("/ask", json={"question": "what colours are there"})
    assert response.status_code == 200
    assert response.json()["sql"] == "SELECT colour FROM colour"


def test_ask_endpoint_rejects_empty_question(client):
    assert client.post("/ask", json={"question": ""}).status_code == 422


def test_ask_endpoint_hides_internal_errors(client, monkeypatch):
    monkeypatch.setattr(
        app_module, "get_service", lambda: service(prediction=RuntimeError("secret internals"))
    )
    response = client.post("/ask", json={"question": "q"})
    assert response.status_code == 502
    assert "secret internals" not in response.text
    assert response.json()["detail"] == "Something went wrong answering this question."


def test_ask_endpoint_reports_quota_without_provider_details(client, monkeypatch):
    from sqlagent.llm import QuotaExhausted

    error = QuotaExhausted("limit resets in 400s: organization org_01secret on tokens per day")
    monkeypatch.setattr(app_module, "get_service", lambda: service(prediction=error))
    response = client.post("/ask", json={"question": "q"})
    assert response.status_code == 503
    assert "org_01secret" not in response.text


def test_databases_lists_every_database_with_tables(client):
    databases = client.get("/databases").json()
    assert len(databases) == 11
    financial = next(d for d in databases if d["db_id"] == "financial")
    assert "account" in financial["tables"]


def guarded(client, monkeypatch, **guard_kwargs):
    from sqlagent.api.limits import Guard

    guard = Guard(**guard_kwargs)
    monkeypatch.setattr(app_module, "get_service", lambda: service())
    monkeypatch.setattr(app_module, "get_guard", lambda: guard)
    return lambda **kw: client.post("/ask", json={"question": "q"}, **kw)


def test_ask_requires_the_shared_token_when_one_is_configured(client, monkeypatch):
    ask = guarded(client, monkeypatch, token="shared")
    assert ask().status_code == 401
    assert ask(headers={"x-api-token": "wrong"}).status_code == 401
    assert ask(headers={"x-api-token": "shared"}).status_code == 200


def test_ask_stops_at_the_daily_limit(client, monkeypatch):
    ask = guarded(client, monkeypatch, daily_limit=1)
    assert ask().status_code == 200
    response = ask()
    assert response.status_code == 429
    assert response.json()["detail"] == "The demo has answered all it can today. Try again tomorrow."


def test_ask_can_be_paused(client, monkeypatch):
    assert guarded(client, monkeypatch, paused=True)().status_code == 503


def test_health_is_not_gated(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_guard", lambda: None)
    assert client.get("/health").status_code == 200


def test_endpoint_sanitizes_execution_and_validation_errors(client, monkeypatch, caplog):
    prediction = Prediction(
        "SELECT 1",
        details={
            "selected": ["colour"],
            "first_error": "private first error",
            "repair_error": "private repair error",
            "final_error": "private final error",
        },
    )
    monkeypatch.setattr(
        app_module,
        "get_service",
        lambda: service(
            prediction=prediction,
            result=QueryResult(error="private connection details", error_type="db_error"),
        ),
    )
    response = client.post("/ask", json={"question": "q"})
    assert response.status_code == 200
    assert "private" not in response.text
    assert response.json()["error"] == "Unable to answer this question. Try rephrasing it."
    assert response.json()["details"] == {"selected": ["colour"]}
    assert "private connection details" in caplog.text
    assert prediction.details["first_error"] == "private first error"


def test_readiness_initializes_service_and_checks_database(client, monkeypatch):
    calls = []
    monkeypatch.setattr(app_module, "get_service", lambda: calls.append("service"))
    monkeypatch.setattr(app_module.db, "assert_read_only_role", lambda: calls.append("database"))
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert calls == ["service", "database"]


@pytest.mark.parametrize("component", ["service", "database"])
def test_readiness_reports_unavailable_without_leaking_errors(client, monkeypatch, component):
    def fail():
        raise RuntimeError("private configuration")

    monkeypatch.setattr(app_module, "get_service", fail if component == "service" else lambda: service())
    monkeypatch.setattr(app_module.db, "assert_read_only_role", fail)
    response = client.get("/ready")
    assert response.status_code == 503
    assert "private" not in response.text
    assert client.get("/health").status_code == 200


def test_provider_failure_returns_generic_service_unavailable(client, monkeypatch):
    from sqlagent.llm import ProviderUnavailable

    monkeypatch.setattr(
        app_module, "get_service", lambda: service(prediction=ProviderUnavailable("private auth"))
    )
    response = client.post("/ask", json={"question": "q"})
    assert response.status_code == 503
    assert "private auth" not in response.text
    assert "unavailable" in response.json()["detail"]


def test_request_id_correlates_generation_and_execution():
    strategy = FakeStrategy(PREDICTION)
    calls = []

    def execute(sql, **kwargs):
        calls.append(kwargs)
        return ROWS

    answer = AskService(strategy, execute=execute).ask("q", request_id="request-123")
    assert answer["request_id"] == "request-123"
    assert strategy.questions[0].question_id == "request-123"
    assert calls[0]["question_id"] == "request-123"
