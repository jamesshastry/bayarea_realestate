"""Smoke tests — the API boots and exposes its OpenAPI + status endpoints.

These tests deliberately do NOT touch the database. They cover only the
"empty checkout" case so a fresh clone can pass `pytest` before Neon is
provisioned.
"""

from __future__ import annotations

from bayre_api.main import app
from fastapi.testclient import TestClient


def test_openapi_renders() -> None:
    """`/openapi.json` returns 200 and a parseable spec with our routes."""
    client = TestClient(app)
    resp = client.get("/openapi.json")
    assert resp.status_code == 200, resp.text

    spec = resp.json()
    assert spec["openapi"].startswith("3.")
    paths = spec["paths"]

    # Every router must contribute at least one path.
    assert "/v1/status" in paths
    assert "/v1/health" in paths
    assert "/v1/areas/search" in paths
    assert "/v1/finance/affordability" in paths


def test_status_endpoint_returns_unknown_with_no_data_file() -> None:
    """`/v1/status` is the public status page (NF-DAT-08) — must be reachable
    even before Phase 0 sources.json exists."""
    client = TestClient(app)
    resp = client.get("/v1/status")
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["overall"] in {"green", "yellow", "red", "unknown"}
    assert isinstance(body["sources"], list)


def test_health_endpoint() -> None:
    client = TestClient(app)
    resp = client.get("/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_stub_routes_return_501() -> None:
    """Unimplemented routes must explicitly say so (501), never silently 500
    or fall through to a generic 404 — that's the contract the frontend
    codegen relies on while Phase 2 is in progress."""
    client = TestClient(app)
    resp = client.post(
        "/v1/finance/affordability",
        json={
            "annual_income": "300000",
            "monthly_debt": "0",
            "down_payment": "150000",
            "rate": "0.065",
            "term_years": 30,
        },
    )
    assert resp.status_code == 501
