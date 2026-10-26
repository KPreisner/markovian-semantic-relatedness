# syntax=docker/dockerfile:1
# One Dockerfile for every Python service; MEMBER picks the workspace member (msr-build, msr-api,
# msr-worker) and Compose gives each service its command.
#
#   develop  MEMBER and its dependencies plus the dev tools; a compose-overrides/ file
#            bind-mounts packages/ over it for hot reload
#   test     the whole workspace plus psql and envsubst, for the integration tests (`test`)
#   builder  wheels for MEMBER, its workspace dependencies, and its locked dependencies
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


# The workspace's manifests, so dependency layers survive source changes.
FROM base AS workspace
COPY --from=uv /uv /uvx /usr/local/bin/
ENV UV_PROJECT_ENVIRONMENT=/venv \
    UV_LINK_MODE=copy \
    PATH=/venv/bin:$PATH
WORKDIR /app
RUN mkdir /venv && chown appuser:appuser /app /venv
COPY --chown=appuser:appuser pyproject.toml uv.lock ./
COPY --chown=appuser:appuser packages/msr-core/pyproject.toml packages/msr-core/
COPY --chown=appuser:appuser packages/msr-nlp/pyproject.toml packages/msr-nlp/
COPY --chown=appuser:appuser packages/msr-db/pyproject.toml packages/msr-db/
COPY --chown=appuser:appuser packages/msr-api/pyproject.toml packages/msr-api/
COPY --chown=appuser:appuser packages/msr-worker/pyproject.toml packages/msr-worker/
COPY --chown=appuser:appuser packages/msr-build/pyproject.toml packages/msr-build/


FROM workspace AS develop
ARG MEMBER=msr-build
USER appuser
RUN --mount=type=cache,target=/home/appuser/.cache/uv,uid=1000,gid=1000 \
    uv sync --frozen --package ${MEMBER} --group dev --no-install-workspace
COPY --chown=appuser:appuser packages/ packages/
RUN --mount=type=cache,target=/home/appuser/.cache/uv,uid=1000,gid=1000 \
    uv sync --frozen --package ${MEMBER} --group dev
WORKDIR /


FROM workspace AS test
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client gettext-base \
    && rm -rf /var/lib/apt/lists/*
USER appuser
RUN --mount=type=cache,target=/home/appuser/.cache/uv,uid=1000,gid=1000 \
    uv sync --frozen --all-packages --group dev --no-install-workspace
COPY --chown=appuser:appuser packages/ packages/
RUN --mount=type=cache,target=/home/appuser/.cache/uv,uid=1000,gid=1000 \
    uv sync --frozen --all-packages --group dev


FROM base AS builder
ARG MEMBER=msr-build
COPY --from=uv /uv /uvx /usr/local/bin/
WORKDIR /src
COPY pyproject.toml uv.lock ./
COPY packages/ packages/
# Locked third-party wheels (hash-checked), then one wheel per workspace member in the closure.
RUN --mount=type=cache,target=/root/.cache/pip \
    uv export --frozen --package ${MEMBER} --no-dev --no-emit-workspace --no-header \
        -o /requirements.txt \
    && pip wheel --no-deps --require-hashes --wheel-dir /wheels -r /requirements.txt
RUN --mount=type=cache,target=/root/.cache/uv \
    for member in $(uv export --frozen --package ${MEMBER} --no-dev --no-hashes --no-header \
                    | sed -n 's|^-e \./packages/||p'); do \
        uv build --package "$member" --wheel --out-dir /wheels || exit 1; \
    done


FROM base AS final
RUN --mount=type=bind,from=builder,source=/wheels,target=/wheels \
    pip install --no-index --no-cache-dir --root-user-action=ignore /wheels/*.whl
USER appuser
WORKDIR /
