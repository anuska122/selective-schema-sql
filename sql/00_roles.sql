\set ON_ERROR_STOP on

SELECT 'CREATE ROLE sqlagent_ro' WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sqlagent_ro')
\gexec

ALTER ROLE sqlagent_ro WITH LOGIN PASSWORD :'ro_password'
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT 20;

REVOKE ALL ON DATABASE bird, postgres, template1 FROM PUBLIC;
GRANT CONNECT ON DATABASE bird TO sqlagent_ro;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO sqlagent_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO sqlagent_ro;

REVOKE EXECUTE ON FUNCTION
    lo_create(oid), lo_creat(integer), lo_from_bytea(oid, bytea),
    lo_put(oid, bigint, bytea), lowrite(integer, bytea)
FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION set_config(text, text, boolean) FROM PUBLIC;
REVOKE USAGE ON LANGUAGE plpgsql FROM PUBLIC;

-- The role can ALTER ROLE its own user-settable defaults; reset them on every apply.
ALTER ROLE sqlagent_ro RESET ALL;
ALTER ROLE sqlagent_ro IN DATABASE bird RESET ALL;
ALTER ROLE sqlagent_ro SET default_transaction_read_only = on;
ALTER ROLE sqlagent_ro SET statement_timeout = '10s';
ALTER ROLE sqlagent_ro SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE sqlagent_ro SET temp_file_limit = '100MB';
