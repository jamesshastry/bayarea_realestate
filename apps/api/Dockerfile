# Multi-stage build for the FastAPI service.
#
# Stage 1 (builder) — uv installs deps into a relocatable /app/.venv. Building
# in a separate stage means the runtime image carries no toolchain, no apt
# cache, no source archives.
#
# Stage 2 (runtime) — Python slim + the prepared venv + the source. Runs as
# an unprivileged user. Listens on $PORT (Railway / Vercel both inject this).

ARG PYTHON_VERSION=3.12

# ── Builder ──────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS builder

# Get uv from the official image — no apt detour required.
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy only manifests first so dependency resolution layer-caches well.
COPY apps/api/pyproject.toml /app/pyproject.toml

# Resolve + install runtime deps into /app/.venv. We pass --no-dev because
# the production image doesn't need pytest / httpx.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv && \
    uv pip install --python /app/.venv/bin/python --no-deps . || true && \
    uv pip install --python /app/.venv/bin/python \
      "fastapi>=0.115" \
      "uvicorn[standard]>=0.30" \
      "sqlalchemy[asyncio]>=2.0" \
      "geoalchemy2>=0.15" \
      "alembic>=1.13" \
      "asyncpg>=0.29" \
      "pydantic>=2.7" \
      "pydantic-settings>=2.4" \
      "python-dotenv>=1.0"

# Copy source last — small layer, changes most often.
COPY apps/api/src /app/src


# ── Runtime ──────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH=/app/src

# Non-root user.
RUN groupadd --system --gid 1001 app && \
    useradd  --system --uid 1001 --gid app --home-dir /app --shell /sbin/nologin app

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src

USER app

# Railway / Fly / generic PaaS inject $PORT; default to 8000 for local docker run.
ENV PORT=8000
EXPOSE 8000

# Honor $PORT via shell form so the env var expands at start time.
CMD ["sh", "-c", "uvicorn bayre_api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
