"""seed the 18 priority GeographicArea rows from docs/seed-data.md §6

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-11

Materializes `docs/seed-data.md` §6: the Bay Area metro + 2 counties + 7
priority cities + 5 school districts + 3 school zones (= 18 rows).

`geometry` is left NULL on every row — boundary ingest is a separate Phase 2
ETL deliverable (Census TIGER for cities/counties, district publications for
school zones). The §9 acceptance queries from `docs/seed-data.md` count rows
by `kind`, not by polygon presence, so this migration alone is enough to
unblock the queries.

`metro_id` is set to the bay-area row's id on every member via a CTE that
resolves the id at INSERT time — avoids hard-coding UUIDs.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── Seed rows (mirror docs/seed-data.md §6) ────────────────────────────────


def upgrade() -> None:
    # 1. Metro
    op.execute(
        """
        INSERT INTO geographic_area (kind, name, slug, metadata)
        VALUES ('metro', 'Bay Area', 'bay-area', '{}'::jsonb);
        """
    )

    # 2. Backfill bay-area's metro_id to itself, so the "everything in metro"
    #    queries (idx_geo_kind_metro) work cleanly without NULL handling.
    op.execute(
        """
        UPDATE geographic_area
        SET metro_id = id
        WHERE slug = 'bay-area' AND kind = 'metro';
        """
    )

    # 3. Counties — parent = bay-area metro.
    _insert_with_parent_metro(
        kind="county",
        rows=[
            ("Alameda County", "alameda", '{"fips": "06001"}'),
            ("Santa Clara County", "santa-clara", '{"fips": "06085"}'),
        ],
        parent_slug="bay-area",
        parent_kind="metro",
    )

    # 4. Cities — parents are the counties above.
    _insert_with_parent_metro(
        kind="city",
        rows=[
            ("Dublin", "dublin", "{}"),
            ("Pleasanton", "pleasanton", "{}"),
            ("Fremont", "fremont", "{}"),
        ],
        parent_slug="alameda",
        parent_kind="county",
    )
    _insert_with_parent_metro(
        kind="city",
        rows=[
            ("Milpitas", "milpitas", "{}"),
            ("Sunnyvale", "sunnyvale", "{}"),
            ("Mountain View", "mountain-view", "{}"),
            ("Campbell", "campbell", "{}"),
        ],
        parent_slug="santa-clara",
        parent_kind="county",
    )

    # 5. School districts — parents are counties (per the data-model:
    #    `kind='school_district' parent=county`).
    _insert_with_parent_metro(
        kind="school_district",
        rows=[
            ("Pleasanton Unified School District", "pleasanton-usd", "{}"),
            ("Dublin Unified School District", "dublin-usd", "{}"),
            ("Fremont Unified School District", "fremont-usd", "{}"),
        ],
        parent_slug="alameda",
        parent_kind="county",
    )
    _insert_with_parent_metro(
        kind="school_district",
        rows=[
            ("Fremont Union High School District", "fuhsd", "{}"),
            (
                "Mountain View – Los Altos Union HSD",
                "mvla",
                "{}",
            ),
        ],
        parent_slug="santa-clara",
        parent_kind="county",
    )

    # 6. School zones — parent_id is the city the school sits in.
    #    Metadata carries `{school_id, level}` per datamodel.md §3.2; the
    #    school_id is filled in by Phase 3 ingest once the `school` rows exist.
    _insert_with_parent_metro(
        kind="school_zone",
        rows=[
            (
                "Foothill HS attendance area",
                "foothill-pleasanton-zone",
                '{"level": "high", "school_cds": "01751010130096"}',
            ),
        ],
        parent_slug="pleasanton",
        parent_kind="city",
    )
    _insert_with_parent_metro(
        kind="school_zone",
        rows=[
            (
                "Fremont HS (Sunnyvale) attendance area",
                "fremont-sunnyvale-zone",
                '{"level": "high", "school_cds": "43694684332474"}',
            ),
        ],
        parent_slug="sunnyvale",
        parent_kind="city",
    )
    _insert_with_parent_metro(
        kind="school_zone",
        rows=[
            (
                "Dublin HS attendance area",
                "dublin-dublin-zone",
                '{"level": "high", "school_cds": "01750930132704"}',
            ),
        ],
        parent_slug="dublin",
        parent_kind="city",
    )


def downgrade() -> None:
    # Children first — school_zones, then school_districts, then cities, etc.
    op.execute(
        """
        DELETE FROM geographic_area
        WHERE slug IN (
          'foothill-pleasanton-zone', 'fremont-sunnyvale-zone', 'dublin-dublin-zone',
          'pleasanton-usd', 'dublin-usd', 'fremont-usd', 'fuhsd', 'mvla',
          'dublin', 'pleasanton', 'fremont',
          'milpitas', 'sunnyvale', 'mountain-view', 'campbell',
          'alameda', 'santa-clara',
          'bay-area'
        );
        """
    )


# ── helpers ────────────────────────────────────────────────────────────────


def _insert_with_parent_metro(
    *,
    kind: str,
    rows: list[tuple[str, str, str]],
    parent_slug: str,
    parent_kind: str,
) -> None:
    """Insert rows whose parent is identified by (slug, kind), and copy the
    bay-area metro id into metro_id automatically.

    Uses a CTE so we never hard-code UUIDs in migrations.
    """
    for name, slug, metadata_json in rows:
        op.execute(
            f"""
            WITH parent AS (
              SELECT id FROM geographic_area
              WHERE slug = '{parent_slug}' AND kind = '{parent_kind}'
            ),
            metro AS (
              SELECT id FROM geographic_area WHERE slug = 'bay-area' AND kind = 'metro'
            )
            INSERT INTO geographic_area (kind, name, slug, parent_id, metro_id, metadata)
            SELECT '{kind}',
                   '{_q(name)}',
                   '{slug}',
                   parent.id,
                   metro.id,
                   '{metadata_json}'::jsonb
            FROM parent, metro;
            """
        )


def _q(s: str) -> str:
    """Single-quote escape for embedding in a SQL literal."""
    return s.replace("'", "''")
