"""Alembic env — async, reads `DATABASE_URL_DIRECT`.

Why direct (not pooled) for migrations:
- pgBouncer transaction-mode pooling (Neon's `-pooler` host) breaks server-
  managed cursors, advisory locks, `CREATE TYPE`, and several other
  statements Alembic relies on.
- Phase 2 keeps the convention from `docs/design.md` §9.1.2:
    DATABASE_URL          → pooled,  for runtime
    DATABASE_URL_DIRECT   → direct,  for Alembic only

The async engine + `connection.run_sync(do_migrations)` pattern is the
SQLAlchemy 2.0 / Alembic 1.13 recommendation for asyncpg-driven projects.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Make `bayre_api.models` importable regardless of where alembic is invoked from.
# Repo root is two levels up from this file (infra/migrations/env.py → repo).
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "apps" / "api" / "src"))

# Load `.env` from the repo root before reading DATABASE_URL_DIRECT. Avoids the
# `set -a; . .env` shell trick, which mis-parses `&` in connection strings.
try:
    from dotenv import load_dotenv

    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    # python-dotenv is optional — env vars set externally still work.
    pass

# Importing the models package registers every table on `Base.metadata`.
from bayre_api.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding", "sslrootcert", "sslcert", "sslkey"}


def _normalize_async_url(url: str) -> str:
    """Coerce vanilla `postgresql://` → `postgresql+asyncpg://` and strip libpq
    query params asyncpg doesn't accept (`sslmode`, `channel_binding`, …).

    Neon's connection string uses libpq syntax (`?sslmode=require&channel_binding=require`),
    but asyncpg uses `ssl=` directly via `connect_args`. We pop the libpq-specific
    params here and `_async_connect_args()` re-introduces SSL via the asyncpg API.
    """
    from urllib.parse import urlencode, urlsplit, urlunsplit

    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://") :]

    parts = urlsplit(url)
    qs_pairs = [
        (k, v)
        for k, v in [p.split("=", 1) for p in parts.query.split("&") if "=" in p]
        if k not in _LIBPQ_ONLY_PARAMS
    ]
    cleaned_query = urlencode(qs_pairs)
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, cleaned_query, parts.fragment)
    )


def _async_connect_args() -> dict[str, object]:
    """asyncpg connect_args that mirror Neon's `?sslmode=require&channel_binding=require`."""
    return {"ssl": "require"}


def _get_url() -> str:
    url = os.environ.get("DATABASE_URL_DIRECT")
    if not url:
        raise RuntimeError(
            "DATABASE_URL_DIRECT is not set. Alembic migrations require the "
            "DIRECT (non-pooled) Neon connection string. See `.env.example`."
        )
    return _normalize_async_url(url)


def run_migrations_offline() -> None:
    """Generate SQL without connecting (useful for review / patching)."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # The `sale` materialized view is mapped read-only; skip it on autogenerate.
        include_object=lambda obj, name, type_, reflected, compare_to: (
            not (type_ == "table" and getattr(obj, "info", {}).get("is_view"))
        ),
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {}) or {}
    cfg["sqlalchemy.url"] = _get_url()

    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
        connect_args=_async_connect_args(),
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
