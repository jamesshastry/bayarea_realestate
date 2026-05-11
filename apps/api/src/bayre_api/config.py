"""Runtime configuration for the FastAPI app.

Reads environment variables (via `pydantic-settings`) from the process env and
optionally a `.env` file at the repo root. The `.env` file is gitignored; see
`.env.example` at the repo root for the canonical template.

Connection-string convention (per `docs/design.md` §9.1.2):
- `DATABASE_URL`        — pooled (`-pooler` host) — used by app code at runtime
- `DATABASE_URL_DIRECT` — direct (no pooler) — used by Alembic migrations only
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Walk up from this file to find the repo root (contains a `.env.example`).
# Resolves to <repo>/apps/api/src/bayre_api/config.py → <repo>.
_REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """All runtime configuration. Inject via `Depends(get_settings)`."""

    model_config = SettingsConfigDict(
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Identity ────────────────────────────────────────────────────────────
    app_name: str = "bayre-api"
    api_version: str = "v1"
    environment: str = Field(default="development")

    # ── Database ────────────────────────────────────────────────────────────
    # Pooled (use everywhere except Alembic). Optional in scaffold so the smoke
    # test can boot without a real DB.
    database_url: str | None = None
    # Direct (Alembic-only). Read by `infra/migrations/env.py`, not by app code.
    database_url_direct: str | None = None

    # ── Auth (Phase 4) ──────────────────────────────────────────────────────
    nextauth_secret: str | None = None
    jwt_secret: str | None = None

    # ── External integrations (kept here so all env reads route through one
    # type-checked surface; populated as Phase 2+ wires each adapter). ─────
    fred_api_key: str | None = None
    mapbox_token: str | None = None
    greatschools_api_key: str | None = None

    # ── Observability ──────────────────────────────────────────────────────
    sentry_dsn: str | None = None
    axiom_token: str | None = None
    axiom_dataset: str | None = None

    # ── Filesystem ─────────────────────────────────────────────────────────
    # Used by the status router to read `data/sources.json` (Phase 0 artifact).
    repo_root: Path = _REPO_ROOT


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor — instantiation reads env, so do it once per process."""
    return Settings()
