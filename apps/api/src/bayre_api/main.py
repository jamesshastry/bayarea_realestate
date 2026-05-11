"""FastAPI app factory + router mounting.

Boots without a database — only `/v1/health`, `/v1/status`, and `/openapi.json`
work in the empty-checkout case. Every data-bearing route raises 501 until
Phase 2 ETL is wired and Neon is provisioned.

Run locally:

    uv run uvicorn bayre_api.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bayre_api import __version__
from bayre_api.config import get_settings
from bayre_api.routers import areas, finance
from bayre_api.routers import status as status_router


def create_app() -> FastAPI:
    """Assemble the FastAPI app — kept as a factory so tests can spin
    isolated instances without process-global side effects."""

    get_settings()
    app = FastAPI(
        title="Bay Area RE — API",
        version=__version__,
        description=(
            "FastAPI backend for the Bay Area first-time-home-buyer "
            "decision-support tool. See `docs/design.md` §6 for the route "
            "surface and `docs/datamodel.md` for the underlying schema."
        ),
        # OpenAPI is committed to the repo (see `apps/api/openapi.json`); the
        # frontend codegen lives at `apps/web/src/api/generated/`.
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — Vercel preview URLs + localhost for dev. Tightened in Phase 2
    # once the deployed frontend's domain is fixed.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "https://*.vercel.app",
        ],
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    # Mount routers. Order doesn't matter, but grouping does for the OpenAPI tag list.
    app.include_router(status_router.router)
    app.include_router(areas.router)
    app.include_router(finance.router)

    return app


# Module-level app instance for `uvicorn bayre_api.main:app`.
app = create_app()
