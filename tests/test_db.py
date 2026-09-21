import json
import os

import psycopg
import pytest

from sqlagent import config, db


@pytest.fixture(scope="module")
def database():
    try:
        psycopg.connect(config.ro_dsn(), connect_timeout=3).close()
    except (psycopg.OperationalError, KeyError) as e:
        if os.environ.get("REQUIRE_DB"):
            raise
        pytest.skip(f"database not reachable: {e}")


@pytest.fixture
def audit(tmp_path):
    return tmp_path / "audit.jsonl"


def run(query, audit, **kw):
    return db.execute(query, caller="test", question_id=7, audit_path=audit, **kw)


def audit_records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.parametrize(
    "query",
    [
        "SELECT 1",
        "select id from colour where id = 1;",
        "SELECT 1 UNION SELECT 2",
        "WITH c AS (SELECT id FROM colour) SELECT count(*) FROM c",
        "SELECT (SELECT max(id) FROM colour) AS m",
    ],
)
def test_validate_accepts_read_only_queries(query):
    assert db.validate_select(query) == query.strip().rstrip(";")


@pytest.mark.parametrize(
    "query",
    [
        "",
        "SELECT 1; SELECT 2",
        "SELECT 1; SET statement_timeout = 0",
        "SET statement_timeout = 0",
        "ALTER ROLE sqlagent_ro SET statement_timeout = 0",
        "INSERT INTO colour VALUES (3, 'x')",
        "UPDATE colour SET colour = 'x'",
        "DELETE FROM colour",
        "TRUNCATE colour",
        "DROP TABLE colour",
        "CREATE TABLE t (x int)",
        "WITH d AS (DELETE FROM colour RETURNING *) SELECT * FROM d",
        "SELECT * INTO t FROM colour",
        "SELECT * FROM colour FOR UPDATE",
        "COPY colour TO STDOUT",
        "EXPLAIN ANALYZE SELECT 1",
        "BEGIN",
        "GRANT SELECT ON colour TO PUBLIC",
        "DO $$ BEGIN PERFORM 1; END $$",
        "SELEC 1 FROM",
    ],
)
def test_validate_rejects(query):
    with pytest.raises(db.RejectedQuery):
        db.validate_select(query)


def test_rejected_query_is_audited_without_touching_database(audit, monkeypatch):
    def fail(*a, **k):
        raise AssertionError("database must not be contacted")

    monkeypatch.setattr(db.psycopg, "connect", fail)
    result = run("DELETE FROM colour", audit)
    assert result.error_type == "rejected"
    assert not result.ok
    (record,) = audit_records(audit)
    assert record["error_type"] == "rejected"
    assert record["sql"] == "DELETE FROM colour"


def test_returns_rows_and_columns(database, audit):
    result = run("SELECT id, colour FROM colour ORDER BY id", audit)
    assert result.ok
    assert result.columns == ["id", "colour"]
    assert result.rows[0][0] == 1
    assert result.truncated is False


def test_truncates_above_row_cap(database, audit):
    result = run("SELECT generate_series(1, 5)", audit, max_rows=3)
    assert [r[0] for r in result.rows] == [1, 2, 3]
    assert result.truncated is True
    assert audit_records(audit)[0]["truncated"] is True


def test_exactly_row_cap_is_not_truncated(database, audit):
    result = run("SELECT generate_series(1, 3)", audit, max_rows=3)
    assert len(result.rows) == 3
    assert result.truncated is False


def test_per_call_timeout_overrides_role_default(database, audit):
    result = run("SELECT pg_sleep(5)", audit, timeout_ms=200)
    assert result.error_type == "timeout"
    assert result.duration_ms < 3000


def test_database_error_is_captured(database, audit):
    result = run("SELECT no_such_column FROM colour", audit)
    assert result.error_type == "db_error"
    assert "no_such_column" in result.error


def test_audit_record_fields(database, audit):
    run("SELECT 1", audit)
    run("SELECT 2", audit)
    records = audit_records(audit)
    assert len(records) == 2
    assert set(records[0]) == {
        "ts",
        "caller",
        "question_id",
        "sql",
        "rows",
        "truncated",
        "duration_ms",
        "error_type",
        "error",
    }
    assert records[0]["caller"] == "test"
    assert records[0]["question_id"] == 7
    assert records[0]["rows"] == 1


def test_server_cursor_blocks_multi_statement_even_if_validator_bypassed(database, audit, monkeypatch):
    monkeypatch.setattr(db, "validate_select", lambda q: q)
    result = run("SELECT 1; SET statement_timeout = 0", audit)
    assert result.error_type == "db_error"
    assert "multiple commands" in result.error


def test_there_is_no_way_to_skip_validation():
    import inspect

    for function in (db.execute, db.explain):
        assert "skip_validation" not in inspect.signature(function).parameters


def test_explain_rejects_non_select_before_the_database(audit, monkeypatch):
    monkeypatch.setattr(
        db.psycopg, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("contacted"))
    )
    result = db.explain("DROP TABLE colour", caller="test", audit_path=audit)
    assert result.error_type == "rejected"
    assert audit_records(audit)[0]["error_type"] == "rejected"


def test_explain_runs_valid_sql(database, audit):
    assert db.explain("SELECT count(*) FROM colour", caller="test", audit_path=audit).ok
    bad = db.explain("SELECT nope FROM colour", caller="test", audit_path=audit)
    assert bad.error_type == "db_error"
