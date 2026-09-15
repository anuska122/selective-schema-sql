import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from sqlagent import config
from sqlagent.eval.types import StageTrace

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GENERATOR_MODEL = "openai/gpt-oss-120b"
SELECTOR_MODEL = "openai/gpt-oss-20b"
REASONING_EFFORT = "medium"

# USD per 1M tokens, Groq list prices as of 2026-09-15.
PRICES = {
    "openai/gpt-oss-120b": {"input": 0.15, "cached_input": 0.075, "output": 0.60},
    "openai/gpt-oss-20b": {"input": 0.075, "cached_input": 0.037, "output": 0.30},
}

MAX_WAIT_S = 120.0
MAX_ATTEMPTS = 5


class LLMError(RuntimeError):
    pass


class QuotaExhausted(LLMError):
    pass


@dataclass(frozen=True)
class LLMResponse:
    text: str
    trace: StageTrace


_DURATION = re.compile(
    r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m(?!s))?(?:(\d+(?:\.\d+)?)s)?(?:(\d+(?:\.\d+)?)ms)?$"
)


def parse_duration(value: str | None) -> float | None:
    if not value:
        return None
    match = _DURATION.fullmatch(value.strip())
    if not match or not any(match.groups()):
        try:
            return float(value)
        except ValueError:
            return None
    h, m, s, ms = (float(g) if g else 0.0 for g in match.groups())
    return h * 3600 + m * 60 + s + ms / 1000


class GroqClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_wait_s: float = MAX_WAIT_S,
    ):
        if api_key is None:
            config.load_env()
            api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise LLMError("GROQ_API_KEY is not set")
        self._http = http or httpx.Client(timeout=120)
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._sleep = sleep
        self._clock = clock
        self._max_wait_s = max_wait_s
        self._budget: dict[str, tuple[int, float]] = {}

    def complete(
        self,
        messages: list[dict],
        *,
        stage: str,
        model: str = GENERATOR_MODEL,
        reasoning_effort: str = REASONING_EFFORT,
        expected_tokens: int = 0,
    ) -> LLMResponse:
        body = {
            "model": model,
            "messages": messages,
            "temperature": 0,
            "reasoning_effort": reasoning_effort,
        }
        waited = self._wait_for_budget(model, expected_tokens)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            start = self._clock()
            response = self._http.post(GROQ_URL, headers=self._headers, json=body)
            latency_ms = (self._clock() - start) * 1000
            self._record_budget(model, response.headers)

            if response.status_code == 200:
                return self._parse(response.json(), stage, model, latency_ms, waited)
            if response.status_code == 429 or response.status_code >= 500:
                delay = parse_duration(response.headers.get("retry-after")) or 2.0**attempt
                if delay > self._max_wait_s:
                    detail = response.text[:200]
                    raise QuotaExhausted(
                        f"{model} limit resets in {delay:.0f}s (likely the daily quota): {detail}"
                    )
                if attempt < MAX_ATTEMPTS:
                    self._sleep(delay)
                    waited += delay * 1000
                    continue
            raise LLMError(f"{model} HTTP {response.status_code}: {response.text[:300]}")

    def _wait_for_budget(self, model: str, expected_tokens: int) -> float:
        remaining, reset_at = self._budget.get(model, (None, 0.0))
        if remaining is None or expected_tokens <= remaining:
            return 0.0
        delay = max(0.0, reset_at - self._clock())
        if delay > self._max_wait_s:
            raise QuotaExhausted(f"{model} token budget resets in {delay:.0f}s")
        self._sleep(delay)
        return delay * 1000

    def _record_budget(self, model: str, headers: httpx.Headers) -> None:
        remaining = headers.get("x-ratelimit-remaining-tokens")
        reset = parse_duration(headers.get("x-ratelimit-reset-tokens"))
        if remaining is not None and reset is not None:
            self._budget[model] = (int(remaining), self._clock() + reset)

    @staticmethod
    def _parse(payload: dict, stage: str, model: str, latency_ms: float, waited_ms: float) -> LLMResponse:
        usage = payload.get("usage") or {}
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        text = payload["choices"][0]["message"].get("content") or ""
        return LLMResponse(
            text=text,
            trace=StageTrace(
                name=stage,
                latency_ms=round(latency_ms, 2),
                llm_calls=1,
                model=model,
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                cached_tokens=cached,
                wait_ms=round(waited_ms, 2),
            ),
        )
