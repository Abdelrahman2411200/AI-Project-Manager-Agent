# syntax=docker/dockerfile:1.7

FROM ghcr.io/astral-sh/uv:0.11.29 AS uv
FROM postgres:18-alpine

COPY --from=uv /uv /uvx /bin/
RUN apk add --no-cache coreutils openssl python3

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/aipm-venv

WORKDIR /workspace/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

COPY backend/app ./app
COPY infra/backup /workspace/infra/backup

WORKDIR /workspace
ENTRYPOINT ["sh", "infra/backup/drill.sh"]
