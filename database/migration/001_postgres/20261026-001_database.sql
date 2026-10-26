-- The application database. CREATE DATABASE can't run in a transaction or DO block, so psql's
-- \gexec runs it only when the database is missing.
SELECT format('CREATE DATABASE %I', '${MSR_DB_NAME}')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${MSR_DB_NAME}')
\gexec
