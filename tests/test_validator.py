import pytest

from sqlagent.db import QueryResult
from sqlagent.validation.validator import Validator, check_names, referenced_names

CATALOG = {
    "account": {"account_id", "district_id", "frequency"},
    "loan": {"loan_id", "account_id", "amount"},
}


def ok_explain(sql, **kw):
    return QueryResult(rows=[])


def validator(explain=ok_explain):
    return Validator(CATALOG, explain=explain)


def test_referenced_names_resolves_aliases():
    tables, columns = referenced_names(
        "SELECT a.frequency, l.amount FROM account a JOIN loan l ON l.account_id = a.account_id"
    )
    assert tables == {"account", "loan"}
    assert columns["account"] == {"frequency", "account_id"}
    assert columns["loan"] == {"amount", "account_id"}


def test_unqualified_columns_may_come_from_any_referenced_table():
    assert check_names("SELECT amount, frequency FROM account JOIN loan ON TRUE", CATALOG) == []
    assert check_names("SELECT ghost FROM account", CATALOG) == ["unknown column: ghost"]


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT * FROM ghost", ["unknown table: ghost"]),
        ("SELECT a.ghost FROM account a", ["unknown column: account.ghost"]),
        ("SELECT account.amount FROM account", ["unknown column: account.amount"]),
    ],
)
def test_check_names_reports_unknown_names(sql, expected):
    assert check_names(sql, CATALOG) == expected


def test_valid_sql_passes_every_stage():
    result = validator().validate("SELECT frequency FROM account WHERE account_id = 1")
    assert (result.ok, result.stage) == (True, "ok")


@pytest.mark.parametrize(
    ("sql", "stage"),
    [
        (None, "parse"),
        ("DELETE FROM account", "parse"),
        ("SELECT 1; SELECT 2", "parse"),
        ("SELECT ghost FROM account", "names"),
    ],
)
def test_bad_sql_is_caught_before_the_database(sql, stage):
    calls = []

    def explain(sql, **kw):
        calls.append(sql)
        return QueryResult(rows=[])

    result = validator(explain).validate(sql)
    assert (result.ok, result.stage) == (False, stage)
    assert result.errors
    assert calls == []


def test_explain_failure_is_reported_with_its_message():
    def failing(sql, **kw):
        return QueryResult(error="ORDER BY expressions must appear in select list", error_type="db_error")

    result = validator(failing).validate("SELECT DISTINCT frequency FROM account")
    assert (result.ok, result.stage) == (False, "explain")
    assert "ORDER BY" in result.message


def test_columns_of_an_unknown_table_are_not_reported_twice():
    assert check_names("SELECT g.x FROM ghost g", CATALOG) == ["unknown table: ghost"]
