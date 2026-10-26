# syntax=docker/dockerfile:1
# The builder: the `msr` CLI (msr-build + core + nlp + db). Run-and-exit, never long-running.
#
#   develop  the workspace with dev dependencies; compose-overrides/compose.builder-dev.yaml
#            bind-mounts packages/ over it; it also runs the integration tests (the `test` service)
#   builder  wheels for the member, its workspace dependencies, and its locked dependencies
#   final    a slim image that installs only those wheels, as appuser (uid 1000)
#
# The data tree is a bind mount at /data, and the working directory is /, so the README's
# relative `data/...` paths mean the same thing inside the container as on the host.

ARG PYTHON_IMAGE=python:3.14.9-slim-trixie

FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MSR_DATA_DIR=/data
RUN useradd --uid 1000 --create-home appuser


FROM base AS develop
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_PROJECT_ENVIRONMENT=/venv \
    UV_LINK_MODE=copy \
    PATH=/venv/bin:$PATH
WORKDIR /app
# psql and envsubst, for the integration tests that run database/migration/migrate.sh.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client gettext-base \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir /venv && chown appuser:appuser /app /venv
USER appuser
# Dependencies first, so a source change doesn't reinstall them.
COPY --chown=appuser:appuser pyproject.toml uv.lock ./
COPY --chown=appuser:appuser packages/msr-core/pyproject.toml packages/msr-core/
COPY --chown=appuser:appuser packages/msr-nlp/pyproject.toml packages/msr-nlp/
COPY --chown=appuser:appuser packages/msr-db/pyproject.toml packages/msr-db/
COPY --chown=appuser:appuser packages/msr-api/pyproject.toml packages/msr-api/
COPY --chown=appuser:appuser packages/msr-worker/pyproject.toml packages/msr-worker/
COPY --chown=appuser:appuser packages/msr-build/pyproject.toml packages/msr-build/
RUN --mount=type=cache,target=/home/appuser/.cache/uv,uid=1000,gid=1000 \
    uv sync --frozen --package msr-build --group dev --no-install-workspace
COPY --chown=appuser:appuser packages/ packages/
RUN --mount=type=cache,target=/home/appuser/.cache/uv,uid=1000,gid=1000 \
    uv sync --frozen --package msr-build --group dev
WORKDIR /
CMD ["msr", "--help"]


FROM base AS builder
COPY --from=uv /uv /uvx /usr/local/bin/
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
# Locked third-party wheels (hash-checked), then one wheel per workspace member in the closure.
RUN --mount=type=cache,target=/root/.cache/pip \
    uv export --frozen --package msr-build --no-dev --no-emit-workspace --no-header \
        -o /requirements.txt \
    && pip wheel --no-deps --require-hashes --wheel-dir /wheels -r /requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    for member in $(uv export --frozen --package msr-build --no-dev --no-hashes --no-header \
                    | sed -n 's|^-e \./packages/||p'); do \
        uv build --package "$member" --wheel --out-dir /wheels || exit 1; \
    done


FROM base AS final
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    pip install --no-index --no-cache-dir --root-user-action=ignore /wheels/*.whl
USER appuser
WORKDIR /
CMD ["msr", "--help"]
