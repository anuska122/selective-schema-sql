import os
import time

import psycopg
import pytest
from psycopg import errors

from sqlagent.config import PG_DATABASE, PG_HOST, PG_PORT, RO_ROLE, load_env, ro_dsn


@pytest.fixture
def conn():
    try:
        c = psycopg.connect(ro_dsn(), connect_timeout=3)
    except psycopg.OperationalError as e:
        if os.environ.get("REQUIRE_DB"):
            raise
        pytest.skip(f"database not reachable: {e}")
    yield c
    c.close()


def run_rw(conn, sql: str):
    with conn.transaction():
        conn.execute("SET TRANSACTION READ WRITE")
        conn.execute(sql)


def test_can_read(conn):
    assert conn.execute("SELECT COUNT(*) FROM superhero").fetchone()[0] > 0


def test_role_attributes(conn):
    row = conn.execute(
        "SELECT rolsuper, rolinherit, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
        "FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    assert row == (False, False, False, False, False, False)


WRITES = [
    "INSERT INTO colour (id, colour) VALUES (99999, 'x')",
    "UPDATE colour SET colour = 'x' WHERE id = 1",
    "DELETE FROM colour WHERE id = 1",
    "TRUNCATE colour",
    "CREATE TABLE public.pwned (x int)",
    "SELECT * FROM colour FOR UPDATE",
]


@pytest.mark.parametrize("sql", WRITES)
def test_write_blocked_in_default_mode(conn, sql):
    with pytest.raises((errors.ReadOnlySqlTransaction, errors.InsufficientPrivilege)):
        conn.execute(sql)


@pytest.mark.parametrize("sql", WRITES)
def test_write_blocked_after_read_write(conn, sql):
    with pytest.raises(errors.InsufficientPrivilege):
        run_rw(conn, sql)


def test_temp_table_blocked(conn):
    with pytest.raises(errors.InsufficientPrivilege):
        run_rw(conn, "CREATE TEMP TABLE t (x int)")


@pytest.mark.parametrize(
    "sql",
    ["SELECT lo_create(0)", "SELECT lo_creat(-1)", "SELECT lo_from_bytea(0, 'x'::bytea)"],
)
def test_large_object_write_blocked(conn, sql):
    with pytest.raises(errors.InsufficientPrivilege):
        run_rw(conn, sql)


@pytest.mark.parametrize("sql", ["SELECT nextval('cards_id_seq')", "SELECT setval('cards_id_seq', 1)"])
def test_sequence_write_blocked(conn, sql):
    with pytest.raises(errors.InsufficientPrivilege):
        run_rw(conn, sql)


def test_do_block_blocked(conn):
    with pytest.raises(errors.InsufficientPrivilege):
        conn.execute("DO $$ BEGIN PERFORM 1; END $$")


def test_cannot_connect_to_other_databases():
    load_env()
    for db in ("postgres", "template1"):
        if db == PG_DATABASE:
            continue
        with pytest.raises(psycopg.OperationalError, match="permission denied"):
            psycopg.connect(
                f"host={PG_HOST} port={PG_PORT} dbname={db} user={RO_ROLE} "
                f"password={os.environ['SQLAGENT_RO_PASSWORD']}",
                connect_timeout=3,
            )


def test_statement_timeout_kills_long_query(conn):
    start = time.monotonic()
    with pytest.raises(errors.QueryCanceled):
        conn.execute("SELECT pg_sleep(20)")
    assert 9 < time.monotonic() - start < 15


def test_timeout_cannot_be_lifted_from_select(conn):
    with pytest.raises(errors.InsufficientPrivilege):
        conn.execute("SELECT set_config('statement_timeout', '0', false)")


def test_temp_file_limit_cannot_be_raised(conn):
    assert conn.execute("SHOW temp_file_limit").fetchone()[0] == "100MB"
    with pytest.raises(errors.InsufficientPrivilege):
        conn.execute("SET temp_file_limit = -1")


@pytest.mark.parametrize(
    "sql",
    [
        "ALTER ROLE sqlagent_ro SUPERUSER",
        "ALTER ROLE sqlagent_ro CONNECTION LIMIT -1",
        "ALTER ROLE sqlagent_ro SET temp_file_limit = -1",
    ],
)
def test_cannot_alter_own_attributes(conn, sql):
    with pytest.raises(errors.InsufficientPrivilege):
        run_rw(conn, sql)


EXPECTED_ROLE_SETTINGS = {
    "default_transaction_read_only=on",
    "statement_timeout=10s",
    "idle_in_transaction_session_timeout=30s",
    "temp_file_limit=100MB",
}


def test_role_settings_not_tampered(conn):
    rows = conn.execute(
        "SELECT s.setdatabase, s.setconfig FROM pg_db_role_setting s "
        "JOIN pg_roles r ON r.oid = s.setrole WHERE r.rolname = current_user"
    ).fetchall()
    assert [(db, set(cfg)) for db, cfg in rows] == [(0, EXPECTED_ROLE_SETTINGS)]


# Known gaps Postgres cannot close; db.execute must block these (#6).


def test_known_gap_bare_set_lifts_timeout(conn):
    conn.execute("SET statement_timeout = 0")
    assert conn.execute("SHOW statement_timeout").fetchone()[0] == "0"


@pytest.mark.parametrize(
    "sql",
    [
        "ALTER ROLE sqlagent_ro SET statement_timeout = 0",
        "ALTER ROLE sqlagent_ro SET default_transaction_read_only = off",
        "ALTER ROLE sqlagent_ro IN DATABASE bird SET statement_timeout = 0",
    ],
)
def test_known_gap_role_can_persist_own_defaults(conn, sql):
    with conn.transaction():
        conn.execute("SET TRANSACTION READ WRITE")
        conn.execute(sql)
        raise psycopg.Rollback()
