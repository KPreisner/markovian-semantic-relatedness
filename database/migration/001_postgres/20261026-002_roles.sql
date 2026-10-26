-- Roles. Privileges belong to NOLOGIN group roles; each service logs in as a member whose name
-- carries the environment suffix (msr_api_local), so a connection string for the wrong
-- environment fails to log in. Passwords are reapplied on every run, so changing one in the env
-- files takes effect on the next start.
DO $$
DECLARE
    grp text;
BEGIN
    FOREACH grp IN ARRAY ARRAY['msr_owner', 'msr_api', 'msr_worker', 'msr_builder', 'data_reader']
    LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = grp) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN', grp);
        END IF;
    END LOOP;
END
$$;

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT * FROM (VALUES
            ('msr_owner_${MSR_ENV}', 'msr_owner', '${MSR_DB_OWNER_PASSWORD}'),
            ('msr_api_${MSR_ENV}', 'msr_api', '${MSR_DB_API_PASSWORD}'),
            ('msr_worker_${MSR_ENV}', 'msr_worker', '${MSR_DB_WORKER_PASSWORD}'),
            ('msr_builder_${MSR_ENV}', 'msr_builder', '${MSR_DB_BUILDER_PASSWORD}'),
            ('data_reader_${MSR_ENV}', 'data_reader', '${MSR_DB_READER_PASSWORD}')
        ) AS t (login, grp, password)
    LOOP
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r.login) THEN
            EXECUTE format('CREATE ROLE %I LOGIN', r.login);
        END IF;
        EXECUTE format('ALTER ROLE %I LOGIN PASSWORD %L', r.login, r.password);
        IF NOT pg_has_role(r.login, r.grp, 'MEMBER') THEN
            EXECUTE format('GRANT %I TO %I', r.grp, r.login);
        END IF;
    END LOOP;
END
$$;
