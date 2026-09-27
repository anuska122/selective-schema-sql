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
