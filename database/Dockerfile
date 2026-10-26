# The db image: Postgres plus envsubst, for both the `postgres` service and the one-shot
# `migrate` service (which runs /migration/migrate.sh and exits).
FROM postgres:18.6-trixie

RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext-base \
    && rm -rf /var/lib/apt/lists/*

COPY migration/ /migration/
