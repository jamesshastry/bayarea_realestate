"""Run the docs/seed-data.md §9 acceptance queries against Neon.

Usage:
    uv run python infra/migrations/verify_seed.py

Reads `DATABASE_URL_DIRECT` from `.env` (auto-loaded), connects, and asserts
the seed counts from `docs/seed-data.md` §9. Exits 0 if all pass, 1 on any
mismatch — safe to wire into CI later.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys

import asyncpg
from dotenv import load_dotenv

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")


# (kind, expected_count)
_EXPECTED_COUNTS: dict[str, int] = {
    "metro": 1,
    "county": 2,
    "city": 7,
    "school_district": 5,
    "school_zone": 3,
}


async def main() -> int:
    url = os.environ.get("DATABASE_URL_DIRECT")
    if not url:
        print("ERROR: DATABASE_URL_DIRECT not set", file=sys.stderr)
        return 1

    conn = await asyncpg.connect(url)
    try:
        # 1. Per-kind counts under the bay-area metro.
        rows = await conn.fetch(
            """
            SELECT kind::text AS kind, count(*)::int AS n
            FROM geographic_area
            WHERE metro_id = (
              SELECT id FROM geographic_area WHERE slug='bay-area' AND kind='metro'
            )
            GROUP BY kind
            ORDER BY kind;
            """
        )
        actual = {r["kind"]: r["n"] for r in rows}
        print("Per-kind counts under metro_id = bay-area:")
        ok = True
        for kind, expected in _EXPECTED_COUNTS.items():
            got = actual.get(kind, 0)
            mark = "✓" if got == expected else "✗"
            print(f"  {mark} {kind:<16}  expected {expected}, got {got}")
            if got != expected:
                ok = False

        # Phase 2 has no schools / attendance_zone rows yet — those land in Phase 3
        # per docs/implementation-plan.md. Skip queries 2 & 3 here; they'd fail
        # against an empty `school` table even with correct seed data.
        n_schools = await conn.fetchval("SELECT count(*)::int FROM school")
        print(
            f"\nschool rows: {n_schools} (expected 0 in Phase 2; populated in Phase 3)"
        )

        return 0 if ok else 1
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
