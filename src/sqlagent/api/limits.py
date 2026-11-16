import hashlib
import os
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path

from sqlagent import config

DAILY_QUESTIONS = 100
TRUTHY = {"1", "true", "yes", "on"}


class Rejected(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Guard:
    def __init__(
        self,
        *,
        token: str = "",
        daily_limit: int = DAILY_QUESTIONS,
        paused: bool = False,
        store: Path | None = None,
        hourly_limit: int = 5,
    ):
        self.token = token
        self.daily_limit = daily_limit
        self.paused = paused
        self.store = store
        self.hourly_limit = hourly_limit
        self._lock = threading.Lock()
        self._day = _today()
        self._used = 0

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "Guard":
        if env is None:
            config.load_env()
            env = os.environ
        return cls(
            token=env.get("SQLAGENT_API_TOKEN", ""),
            daily_limit=int(env.get("SQLAGENT_DAILY_QUESTIONS") or DAILY_QUESTIONS),
            paused=env.get("SQLAGENT_PAUSED", "").lower() in TRUTHY,
            store=Path(env["SQLAGENT_LIMIT_DB"]) if env.get("SQLAGENT_LIMIT_DB") else None,
            hourly_limit=int(env.get("SQLAGENT_HOURLY_QUESTIONS") or 5),
        )

    @property
    def used(self) -> int:
        if self.store:
            with closing(self._connect()) as conn:
                row = conn.execute("SELECT used FROM budgets WHERE key = ?", (f"day:{_today()}",)).fetchone()
                return row[0] if row else 0
        with self._lock:
            return self._used if self._day == _today() else 0

    def _connect(self) -> sqlite3.Connection:
        assert self.store is not None
        self.store.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.store, timeout=5)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS budgets (key TEXT PRIMARY KEY, used INTEGER, expires INTEGER)"
        )
        return conn

    def _reserve(self, client_id: str | None) -> None:
        now = int(time.time())
        visitor = hashlib.sha256((client_id if self.token and client_id else "direct").encode()).hexdigest()
        budgets = [
            (
                f"day:{_today()}",
                self.daily_limit,
                now + 86400,
                "The demo has answered all it can today. Try again tomorrow.",
            ),
            (
                f"hour:{now // 3600}:{visitor}",
                self.hourly_limit,
                (now // 3600 + 1) * 3600,
                "Too many questions from here. Try again later.",
            ),
        ]
        # Serialize the check and both increments across API workers sharing this file.
        with closing(self._connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM budgets WHERE expires <= ?", (now,))
            for key, limit, _, detail in budgets:
                row = conn.execute("SELECT used FROM budgets WHERE key = ?", (key,)).fetchone()
                if (row[0] if row else 0) >= limit:
                    raise Rejected(429, detail)
            for key, _, expires, _ in budgets:
                conn.execute(
                    "INSERT INTO budgets VALUES (?, 1, ?) ON CONFLICT(key) DO UPDATE SET used = used + 1",
                    (key, expires),
                )

    def check(self, token: str | None, client_id: str | None = None) -> None:
        if self.paused:
            raise Rejected(503, "The demo is paused.")
        if self.token and not secrets.compare_digest((token or "").encode(), self.token.encode()):
            raise Rejected(401, "Not authorised.")
        if self.store:
            self._reserve(client_id)
            return
        with self._lock:
            today = _today()
            if self._day != today:
                self._day, self._used = today, 0
            if self._used >= self.daily_limit:
                raise Rejected(429, "The demo has answered all it can today. Try again tomorrow.")
            self._used += 1


def _today() -> date:
    return datetime.now(UTC).date()
