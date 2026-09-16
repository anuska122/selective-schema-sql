import json

import httpx
import pytest

from sqlagent import llm
from sqlagent.llm import GroqClient, LLMError, QuotaExhausted, parse_duration

OK_BODY = {
    "choices": [{"message": {"content": "SELECT 1"}}],
    "usage": {
        "prompt_tokens": 1200,
        "completion_tokens": 300,
        "prompt_tokens_details": {"cached_tokens": 1000},
    },
}
BUDGET = {"x-ratelimit-remaining-tokens": "7000", "x-ratelimit-reset-tokens": "7.5s"}


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def client_with(responses, clock=None, **kw):
    queue = list(responses)
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return queue.pop(0)

    clock = clock or FakeClock()
    client = GroqClient(
        "test-key",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=clock.sleep,
        clock=clock,
        **kw,
    )
    return client, requests, clock


@pytest.mark.parametrize(
    ("value", "seconds"),
    [
        ("772ms", 0.772),
        ("7.66s", 7.66),
        ("1m26.4s", 86.4),
        ("2h", 7200),
        ("1h2m3s", 3723),
        ("30", 30.0),
        (None, None),
        ("soon", None),
    ],
)
def test_parse_duration(value, seconds):
    assert parse_duration(value) == (pytest.approx(seconds) if seconds is not None else None)


def test_success_records_usage_and_request_settings():
    client, requests, _ = client_with([httpx.Response(200, json=OK_BODY, headers=BUDGET)])
    response = client.complete([{"role": "user", "content": "q"}], stage="generate")
    assert response.text == "SELECT 1"
    t = response.trace
    assert (t.name, t.llm_calls, t.model) == ("generate", 1, llm.GENERATOR_MODEL)
    assert (t.tokens_in, t.tokens_out, t.cached_tokens, t.wait_ms) == (1200, 300, 1000, 0.0)
    assert requests[0]["temperature"] == 0
    assert requests[0]["reasoning_effort"] == "medium"
    assert requests[0]["model"] == "openai/gpt-oss-120b"


def test_missing_cached_tokens_and_content_default_to_zero_and_empty():
    body = {
        "choices": [{"message": {"content": None}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 1},
    }
    client, _, _ = client_with([httpx.Response(200, json=body)])
    response = client.complete([], stage="s")
    assert response.text == ""
    assert response.trace.cached_tokens == 0


def test_429_waits_retry_after_then_succeeds_and_records_wait():
    client, requests, clock = client_with(
        [
            httpx.Response(429, headers={"retry-after": "3"}, text="slow down"),
            httpx.Response(200, json=OK_BODY),
        ]
    )
    response = client.complete([], stage="s")
    assert len(requests) == 2
    assert clock.sleeps == [3.0]
    assert response.trace.wait_ms == 3000


def test_server_error_backs_off_exponentially():
    client, requests, clock = client_with(
        [httpx.Response(503), httpx.Response(502), httpx.Response(200, json=OK_BODY)]
    )
    client.complete([], stage="s")
    assert clock.sleeps == [2.0, 4.0]


def test_long_retry_after_means_daily_quota_and_fails_fast():
    client, requests, clock = client_with(
        [httpx.Response(429, headers={"retry-after": "3600"}, text="daily")]
    )
    with pytest.raises(QuotaExhausted, match="daily quota"):
        client.complete([], stage="s")
    assert clock.sleeps == []


def test_gives_up_after_max_attempts():
    client, requests, _ = client_with([httpx.Response(429, headers={"retry-after": "1"})] * llm.MAX_ATTEMPTS)
    with pytest.raises(LLMError, match="HTTP 429"):
        client.complete([], stage="s")
    assert len(requests) == llm.MAX_ATTEMPTS


def test_client_error_is_not_retried():
    client, requests, _ = client_with([httpx.Response(401, text="invalid_api_key")])
    with pytest.raises(LLMError, match="401"):
        client.complete([], stage="s")
    assert len(requests) == 1


def test_waits_for_token_budget_before_a_large_request():
    low_budget = {"x-ratelimit-remaining-tokens": "500", "x-ratelimit-reset-tokens": "10s"}
    client, _, clock = client_with(
        [httpx.Response(200, json=OK_BODY, headers=low_budget), httpx.Response(200, json=OK_BODY)]
    )
    client.complete([], stage="s")
    response = client.complete([], stage="s", expected_tokens=4000)
    assert clock.sleeps == [10.0]
    assert response.trace.wait_ms == 10000


def test_small_request_within_budget_does_not_wait():
    client, _, clock = client_with(
        [httpx.Response(200, json=OK_BODY, headers=BUDGET), httpx.Response(200, json=OK_BODY)]
    )
    client.complete([], stage="s")
    client.complete([], stage="s", expected_tokens=1000)
    assert clock.sleeps == []


def test_budget_reset_too_far_away_fails_fast():
    far = {"x-ratelimit-remaining-tokens": "0", "x-ratelimit-reset-tokens": "5m"}
    client, _, _ = client_with([httpx.Response(200, json=OK_BODY, headers=far)])
    client.complete([], stage="s")
    with pytest.raises(QuotaExhausted):
        client.complete([], stage="s", expected_tokens=100)


def test_missing_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(llm.config, "ROOT", tmp_path)
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        GroqClient()


def test_every_model_has_a_price():
    assert set(llm.PRICES) == {llm.GENERATOR_MODEL, llm.SELECTOR_MODEL}
    for price in llm.PRICES.values():
        assert set(price) == {"input", "cached_input", "output"}


def test_json_mode_sets_response_format():
    client, requests, _ = client_with([httpx.Response(200, json=OK_BODY), httpx.Response(200, json=OK_BODY)])
    client.complete([], stage="s", json_mode=True, max_tokens=4096)
    client.complete([], stage="s")
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert requests[0]["max_completion_tokens"] == 4096
    assert "response_format" not in requests[1]
    assert "max_completion_tokens" not in requests[1]
