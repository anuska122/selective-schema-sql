import os
import secrets
import threading
from datetime import UTC, date, datetime

DAILY_QUESTIONS = 100
TRUTHY = {"1", "true", "yes", "on"}


class Rejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Guard:
    def __init__(self, *, token: str = "", daily_limit: int = DAILY_QUESTIONS, paused: bool = False):
        self.token = token
        self.daily_limit = daily_limit
        self.paused = paused
        self._lock = threading.Lock()
        self._day = _today()
        self._used = 0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Guard":
        env = os.environ if env is None else env
        return cls(
            token=env.get("SQLAGENT_API_TOKEN", ""),
            daily_limit=int(env.get("SQLAGENT_DAILY_QUESTIONS") or DAILY_QUESTIONS),
            paused=env.get("SQLAGENT_PAUSED", "").lower() in TRUTHY,
        )

    @property
    def used(self) -> int:
        with self._lock:
            return self._used if self._day == _today() else 0

    def check(self, token: str | None) -> None:
        if self.paused:
            raise Rejected(503, "The demo is paused.")
        if self.token and not secrets.compare_digest(token or "", self.token):
            raise Rejected(401, "Not authorised.")
        with self._lock:
            today = _today()
            if self._day != today:
                self._day, self._used = today, 0
            if self._used >= self.daily_limit:
                raise Rejected(429, "The demo has answered all it can today. Try again tomorrow.")
            self._used += 1


def _today() -> date:
    return datetime.now(UTC).date()
