-- The msr schema, owned by msr_owner, and the privileges that don't depend on any one table.
-- Per-table grants live next to each table in 002_migration/.
\connect ${MSR_DB_NAME}

REVOKE ALL ON DATABASE ${MSR_DB_NAME} FROM PUBLIC;
GRANT CONNECT ON DATABASE ${MSR_DB_NAME} TO msr_owner, msr_api, msr_worker, msr_builder, data_reader;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA IF NOT EXISTS msr AUTHORIZATION msr_owner;
GRANT USAGE ON SCHEMA msr TO msr_api, msr_worker, msr_builder, data_reader;

-- Everything msr_owner creates in msr is readable by data_reader, for ad-hoc analysis.
ALTER DEFAULT PRIVILEGES FOR ROLE msr_owner IN SCHEMA msr GRANT SELECT ON TABLES TO data_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE msr_owner IN SCHEMA msr GRANT SELECT ON SEQUENCES TO data_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE msr_owner IN SCHEMA msr
    GRANT EXECUTE ON FUNCTIONS TO data_reader;

-- The runner's record of applied files, created as msr_owner so the default privileges apply.
SET ROLE msr_owner;
CREATE TABLE IF NOT EXISTS msr.schema_migrations (
    filename text PRIMARY KEY,
    checksum text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);
RESET ROLE;
