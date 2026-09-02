# syntax=docker/dockerfile:1
FROM python:3.12-slim@sha256:2fe5997d249a808b8eeea52c58a1dbffbba28754dc11699ef5c029f2d818ce79

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY README.md pyproject.toml uv.lock ./
COPY src ./src

RUN python -m pip install --no-cache-dir uv==0.8.13 \
    && uv pip install --system --no-cache . pytest==9.0.2 ruff==0.15.12 \
    && rm -rf /build /root/.cache

WORKDIR /workspace/candidate
