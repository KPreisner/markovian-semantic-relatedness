#!/usr/bin/env bash
# The migration runner.
#
#   001_postgres/   idempotent superuser bootstrap (database, roles, schema, default privileges),
#                   run on every start, connected to the maintenance database
#   002_migration/  schema changes, then 003_data/ seed data: each file runs once, as msr_owner,
#                   in one transaction that also records it in msr.schema_migrations
#
# Files run in name order and go through envsubst, limited to MSR_* variables so SQL like `$1` or
# `$$` passes through untouched. An applied file is immutable: if its checksum no longer matches
# the recorded one, the runner fails, and the fix is a new file.
#
# Environment: PGHOST (and optionally PGPORT), POSTGRES_USER / POSTGRES_PASSWORD (the superuser),
# POSTGRES_DB (the maintenance database), MSR_DB_NAME, MSR_ENV, and the MSR_DB_*_PASSWORD values.
# MIGRATION_DIR overrides the directory holding the three folders (default: this script's).
set -euo pipefail

dir=${MIGRATION_DIR:-$(cd "$(dirname "$0")" && pwd)}
: "${PGHOST:?}" "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}" "${MSR_DB_NAME:?}" "${MSR_ENV:?}"
: "${MSR_DB_OWNER_PASSWORD:?}"
export PGOPTIONS="-c client_min_messages=warning"

shell_format=$(compgen -v MSR_ | sed 's/.*/${&}/' | tr '\n' ' ')

render() {
    envsubst "$shell_format" <"$1"
}

as_superuser() {
    PGPASSWORD=$POSTGRES_PASSWORD psql -X -q -v ON_ERROR_STOP=1 \
        -U "$POSTGRES_USER" -d "${POSTGRES_DB:-postgres}" "$@"
}

as_owner() {
    PGPASSWORD=$MSR_DB_OWNER_PASSWORD psql -X -q -v ON_ERROR_STOP=1 \
        -U "msr_owner_$MSR_ENV" -d "$MSR_DB_NAME" "$@"
}

for file in "$dir"/001_postgres/*.sql; do
    echo "migrate: 001_postgres/$(basename "$file")"
    render "$file" | as_superuser -f -
done

applied=0
for stage in 002_migration 003_data; do
    for file in "$dir/$stage"/*.sql; do
        [ -e "$file" ] || continue
        name="$stage/$(basename "$file")"
        checksum=$(sha256sum "$file" | cut -d ' ' -f 1)
        recorded=$(as_owner -tA -v name="$name" -f - <<<"
            SELECT checksum FROM msr.schema_migrations WHERE filename = :'name';")
        if [ -n "$recorded" ]; then
            if [ "$recorded" != "$checksum" ]; then
                echo "migrate: $name changed after it was applied" \
                    "(recorded $recorded, now $checksum); add a new file instead" >&2
                exit 1
            fi
            continue
        fi
        echo "migrate: applying $name"
        {
            echo "SET ROLE msr_owner;"
            render "$file"
            echo
            echo "INSERT INTO msr.schema_migrations (filename, checksum) VALUES (:'name', :'checksum');"
        } | as_owner --single-transaction -v name="$name" -v checksum="$checksum" -f -
        applied=$((applied + 1))
    done
done
echo "migrate: $applied applied"
