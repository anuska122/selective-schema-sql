-- Read-only role for all agent and eval queries. See docs/PLAN.md §4.
-- Idempotent. Run as the admin role against database bird:
--   scripts/apply_roles.sh
--
-- Privileges are the real control. default_transaction_read_only is a second
-- layer only: any session can SET TRANSACTION READ WRITE.
-- Each REVOKE below closes a bypass that tests/test_security.py exercises.

\set ON_ERROR_STOP on

SELECT 'CREATE ROLE sqlagent_ro' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sqlagent_ro')
\gexec

ALTER ROLE sqlagent_ro WITH LOGIN PASSWORD :'ro_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT 20;

-- Database access: CONNECT to bird only. PUBLIC gets CONNECT and TEMP on every
-- database by default.
REVOKE ALL ON DATABASE bird, postgres, template1 FROM PUBLIC;
GRANT CONNECT ON DATABASE bird TO sqlagent_ro;

-- Allowlisted schemas: public only (all BIRD tables live there).
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO sqlagent_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sqlagent_ro;
-- No sequence privileges: nextval/setval are writes.

-- Function-level bypasses reachable from inside a SELECT.
-- Large objects: any role may create one, which is a write.
REVOKE EXECUTE ON FUNCTION
    lo_create(oid), lo_creat(integer), lo_from_bytea(oid, bytea),
    lo_put(oid, bigint, bytea), lowrite(integer, bytea)
FROM PUBLIC;
-- set_config('statement_timeout', '0', false) would lift the timeout from a SELECT.
REVOKE EXECUTE ON FUNCTION set_config(text, text, boolean) FROM PUBLIC;
-- DO blocks can run arbitrary SET/EXECUTE; the agent never needs procedural code.
REVOKE USAGE ON LANGUAGE plpgsql FROM PUBLIC;

-- Resource limits applied at login. Postgres cannot lock user-settable GUCs:
-- the role can override them with a bare SET, and can even persist new
-- defaults with ALTER ROLE sqlagent_ro SET ... (ordinary roles may alter their
-- own defaults). db.execute must accept a single SELECT only and set limits
-- itself on every call (issue #6). RESET ALL here wipes any tampered defaults;
-- tests/test_security.py detects drift.
ALTER ROLE sqlagent_ro RESET ALL;
ALTER ROLE sqlagent_ro IN DATABASE bird RESET ALL;
ALTER ROLE sqlagent_ro SET default_transaction_read_only = on;
ALTER ROLE sqlagent_ro SET statement_timeout = '10s';
ALTER ROLE sqlagent_ro SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE sqlagent_ro SET temp_file_limit = '100MB';  -- superuser-only GUC; the role cannot raise it
