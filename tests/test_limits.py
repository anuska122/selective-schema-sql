from datetime import UTC, datetime, timedelta

import pytest

from sqlagent.api import limits
from sqlagent.api.limits import DAILY_QUESTIONS, Guard, Rejected


@pytest.fixture
def guard():
    return Guard(daily_limit=2)


def test_allows_questions_up_to_the_daily_limit(guard):
    guard.check(None)
    guard.check(None)
    assert guard.used == 2
    with pytest.raises(Rejected) as rejected:
        guard.check(None)
    assert rejected.value.status == 429


def test_the_daily_count_resets_the_next_day(guard, monkeypatch):
    guard.check(None)
    guard.check(None)
    tomorrow = datetime.now(UTC).date() + timedelta(days=1)
    monkeypatch.setattr(limits, "_today", lambda: tomorrow)
    guard.check(None)
    assert guard.used == 1


def test_a_configured_token_is_required_and_compared_in_full():
    guard = Guard(token="secret-token")
    guard.check("secret-token")
    for wrong in (None, "", "secret", "secret-token-plus"):
        with pytest.raises(Rejected) as rejected:
            guard.check(wrong)
        assert rejected.value.status == 401


def test_no_token_configured_means_no_token_required():
    Guard().check(None)


def test_pausing_rejects_everything_even_with_the_right_token():
    guard = Guard(token="t", paused=True)
    with pytest.raises(Rejected) as rejected:
        guard.check("t")
    assert rejected.value.status == 503
    assert guard.used == 0


def test_rejection_details_carry_no_internals():
    guard = Guard(daily_limit=0)
    with pytest.raises(Rejected) as rejected:
        guard.check(None)
    assert "0" not in rejected.value.detail


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, ("", DAILY_QUESTIONS, False)),
        ({"SQLAGENT_API_TOKEN": "t"}, ("t", DAILY_QUESTIONS, False)),
        ({"SQLAGENT_DAILY_QUESTIONS": "7"}, ("", 7, False)),
        ({"SQLAGENT_DAILY_QUESTIONS": ""}, ("", DAILY_QUESTIONS, False)),
        ({"SQLAGENT_PAUSED": "1"}, ("", DAILY_QUESTIONS, True)),
        ({"SQLAGENT_PAUSED": "TRUE"}, ("", DAILY_QUESTIONS, True)),
        ({"SQLAGENT_PAUSED": "0"}, ("", DAILY_QUESTIONS, False)),
        ({"SQLAGENT_PAUSED": ""}, ("", DAILY_QUESTIONS, False)),
    ],
)
def test_from_env(env, expected):
    guard = Guard.from_env(env)
    assert (guard.token, guard.daily_limit, guard.paused) == expected


def test_guard_loads_dotenv_before_reading_authentication_settings(monkeypatch):
    def load():
        monkeypatch.setenv("SQLAGENT_API_TOKEN", "configured-in-dotenv")

    monkeypatch.setattr(limits.config, "load_env", load)
    guard = Guard.from_env()
    with pytest.raises(Rejected) as rejected:
        guard.check(None)
    assert rejected.value.status == 401
    guard.check("configured-in-dotenv")


def test_persistent_limits_are_shared_and_survive_guard_recreation(tmp_path):
    path = tmp_path / "limits.sqlite3"
    first = Guard(token="t", store=path, daily_limit=2, hourly_limit=10)
    first.check("t", "a")
    second = Guard(token="t", store=path, daily_limit=2, hourly_limit=10)
    assert second.used == 1
    second.check("t", "b")
    with pytest.raises(Rejected) as rejected:
        first.check("t", "c")
    assert rejected.value.status == 429
    assert first.used == 2


def test_persistent_hourly_limits_do_not_spend_daily_quota_when_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(limits.time, "time", lambda: 3601)
    guard = Guard(token="t", store=tmp_path / "limits.sqlite3", hourly_limit=1)
    guard.check("t", "a")
    with pytest.raises(Rejected):
        guard.check("t", "a")
    assert guard.used == 1
    guard.check("t", "b")
    monkeypatch.setattr(limits.time, "time", lambda: 7201)
    guard.check("t", "a")
    assert guard.used == 3


def test_concurrent_workers_cannot_overspend_daily_quota(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "limits.sqlite3"

    def reserve(number):
        try:
            Guard(token="t", store=path, daily_limit=5, hourly_limit=100).check("t", str(number))
            return True
        except Rejected:
            return False

    with ThreadPoolExecutor(max_workers=8) as workers:
        assert sum(workers.map(reserve, range(20))) == 5
    assert Guard(store=path).used == 5


def test_persistent_quota_settings_load_from_environment(tmp_path):
    path = tmp_path / "limits.sqlite3"
    guard = Guard.from_env({"SQLAGENT_LIMIT_DB": str(path), "SQLAGENT_HOURLY_QUESTIONS": "2"})
    assert guard.store == path
    assert guard.hourly_limit == 2


def test_invalid_tokens_never_consume_persistent_quota(tmp_path):
    guard = Guard(token="t", store=tmp_path / "limits.sqlite3")
    with pytest.raises(Rejected):
        guard.check("invalid", "a")
    assert guard.used == 0
    with pytest.raises(Rejected):
        guard.check("non-ascii-ñ", "a")


def test_unauthenticated_callers_share_a_bucket_even_if_they_forge_client_ids(tmp_path):
    guard = Guard(store=tmp_path / "limits.sqlite3", hourly_limit=1)
    guard.check(None, "a")
    with pytest.raises(Rejected):
        guard.check(None, "b")
