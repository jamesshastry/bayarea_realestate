"""Async SQLAlchemy 2.0 engine + per-request session dependency.

Phase 2 scaffold: the engine is constructed lazily so the API can boot (and
expose `/openapi.json` + `/v1/status`) without a live database. Once Neon is
provisioned and `DATABASE_URL` is set, every router that depends on
`get_session` receives a real `AsyncSession`.

Connection-string convention is enforced in `config.py`: `DATABASE_URL` is the
pooled connection string for runtime; Alembic migrations use
`DATABASE_URL_DIRECT` (see `infra/migrations/env.py`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bayre_api.config import get_settings

if TYPE_CHECKING:
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _normalize_async_url(url: str) -> str:
    """Coerce a vanilla `postgresql://` URL to `postgresql+asyncpg://`.

    Neon hands out connection strings without the dialect+driver prefix; the
    async engine needs the explicit driver.
    """
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


def get_engine() -> AsyncEngine:
    """Lazily construct (and cache) the async engine.

    Raises `RuntimeError` if `DATABASE_URL` is unset — surfaces config errors
    at the first DB-using request rather than at import time.
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.database_url:
            raise RuntimeError(
                "DATABASE_URL is not set. Set it in `.env` or the process "
                "environment before hitting routes that touch the database."
            )
        _engine = create_async_engine(
            _normalize_async_url(settings.database_url),
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a single AsyncSession per request."""
    sm = get_sessionmaker()
    async with sm() as session:
        yield session
