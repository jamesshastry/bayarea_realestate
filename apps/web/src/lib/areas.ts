/**
 * Typed read-side queries against `geographic_area`.
 *
 * Phase 2 stopgap (see `apps/web/src/lib/db.ts`) — every function here will
 * become a call to `apps/api/v1/areas/...` once Railway is up.
 */

import { getSql } from "./db";

export type CityCard = {
  slug: string;
  name: string;
  county_name: string;
  county_slug: string;
  median_price: string | null;
  period_start: Date | null;
};

/**
 * List the city-kind GeographicArea rows under a metro, joined with their
 * parent county AND their latest market_snapshot's median_price for display.
 *
 * The LATERAL join picks the most-recent snapshot per city without a window
 * function. Cities with no snapshot show median_price = null (the UI falls
 * back to a "no data yet" treatment).
 *
 * Mirrors the SQL the future `/v1/metros/{slug}/cities` endpoint will run.
 */
export async function listCitiesInMetro(metroSlug: string): Promise<CityCard[]> {
  const rows = await getSql()<CityCard[]>`
    SELECT
      city.slug          AS slug,
      city.name          AS name,
      county.name        AS county_name,
      county.slug        AS county_slug,
      latest.median_sale_price::text AS median_price,
      latest.period_start            AS period_start
    FROM geographic_area city
    JOIN geographic_area county ON city.parent_id = county.id
    LEFT JOIN LATERAL (
      SELECT median_sale_price, period_start
      FROM market_snapshot ms
      WHERE ms.area_id = city.id
        AND ms.property_type = 'sfh'
      ORDER BY period_start DESC
      LIMIT 1
    ) latest ON true
    WHERE city.kind = 'city'
      AND city.metro_id = (
        SELECT id
        FROM geographic_area
        WHERE slug = ${metroSlug} AND kind = 'metro'
      )
    ORDER BY city.name;
  `;
  return rows;
}

export type CityDetail = {
  slug: string;
  name: string;
  county_name: string;
  metro_slug: string;
  metro_name: string;
};

export type CitySnapshotRow = {
  period_kind: string;
  period_start: Date;
  period_end: Date;
  median_sale_price: string | null;
  median_ppsf: string | null;
  median_dom: number | null;
  sale_to_list_ratio: string | null;
  homes_sold: number | null;
  active_listings: number | null;
  new_listings: number | null;
  months_of_supply: string | null;
  pct_with_price_drops: string | null;
  sample_size: number;
  confidence_score: number;
  computed_at: Date;
  source_versions: Record<string, string>;
};

/** Fetch a single city under a metro by both slugs. Returns null if either
 * slug doesn't resolve OR the city isn't actually a child of that metro
 * (defensive — protects against URL fishing for `/bay-area/cities/oakland`). */
export async function getCity(
  metroSlug: string,
  citySlug: string,
): Promise<CityDetail | null> {
  const rows = await getSql()<CityDetail[]>`
    SELECT
      city.slug      AS slug,
      city.name      AS name,
      county.name    AS county_name,
      metro.slug     AS metro_slug,
      metro.name     AS metro_name
    FROM geographic_area city
    JOIN geographic_area county ON city.parent_id = county.id
    JOIN geographic_area metro  ON city.metro_id  = metro.id
    WHERE city.kind = 'city'
      AND city.slug = ${citySlug}
      AND metro.slug = ${metroSlug} AND metro.kind = 'metro';
  `;
  return rows[0] ?? null;
}

export type SchoolListing = {
  cds_code: string;
  name: string;
  level: string;
  district_name: string | null;
};

/** List schools under a metro. Returns empty until Phase 3 ingest lands.
 *
 * The path is `school → school_district.area_id → geographic_area.metro_id`
 * (per `docs/datamodel.md` §4.1's polymorphic design — districts ARE
 * geographic areas of kind='school_district', and they carry the metro_id).
 *
 * Order: by level (high → middle → elementary), then name.
 */
export async function listMetroSchools(metroSlug: string): Promise<SchoolListing[]> {
  const rows = await getSql()<SchoolListing[]>`
    SELECT
      s.cds_code,
      s.name,
      s.level::text  AS level,
      d.name         AS district_name
    FROM school s
    JOIN school_district d ON s.district_id = d.id
    JOIN geographic_area district_area ON d.area_id = district_area.id
    WHERE district_area.metro_id = (
      SELECT id FROM geographic_area WHERE slug = ${metroSlug} AND kind = 'metro'
    )
    ORDER BY
      CASE s.level
        WHEN 'high' THEN 1
        WHEN 'middle' THEN 2
        WHEN 'elementary' THEN 3
        ELSE 4
      END,
      s.name;
  `;
  return rows;
}

export type CityPhaseInput = {
  slug: string;
  name: string;
  county_name: string;
  history_months: number;
  latest_period_end: Date | null;
  /** Latest snapshot's metrics needed by computePhase, when available. */
  median_dom: number | null;
  active_listings: number | null;
  sample_size: number | null;
  confidence_score: number | null;
  median_sale_price: string | null;
  months_of_supply: string | null;
  pct_with_price_drops: string | null;
  /** 1-month median sale_to_list (for the s2l_4w slot). */
  s2l_1m: string | null;
  /** 3-month rolling median sale_to_list (for the s2l_12w slot). */
  s2l_3m: string | null;
};

/**
 * One row per city in a metro: latest snapshot + counts to drive the
 * Phase 2 timing page. When `history_months < 3`, the timing UI shows
 * "data accumulating" instead of a Market Phase classification because
 * `computePhase` needs trailing medians it can't compute yet.
 *
 * The s2l_1m / s2l_3m approximations stand in for the s2l_4w / s2l_12w
 * inputs `computePhase` expects (the function was designed for weekly
 * snapshots; ours are monthly until the Phase 2 RESO MLS feed lands).
 */
export async function listMetroCitiesForTiming(
  metroSlug: string,
): Promise<CityPhaseInput[]> {
  const rows = await getSql()<CityPhaseInput[]>`
    WITH metro AS (
      SELECT id FROM geographic_area WHERE slug = ${metroSlug} AND kind = 'metro'
    ),
    cities AS (
      SELECT city.id, city.slug, city.name, county.name AS county_name
      FROM geographic_area city
      JOIN geographic_area county ON city.parent_id = county.id
      WHERE city.kind = 'city' AND city.metro_id = (SELECT id FROM metro)
    ),
    ranked AS (
      SELECT
        ms.area_id,
        ms.period_end,
        ms.sale_to_list_ratio,
        ms.median_dom,
        ms.active_listings,
        ms.sample_size,
        ms.confidence_score,
        ms.median_sale_price,
        ms.months_of_supply,
        ms.pct_with_price_drops,
        row_number() OVER (PARTITION BY ms.area_id ORDER BY ms.period_start DESC) AS rn
      FROM market_snapshot ms
      WHERE ms.property_type = 'sfh' AND ms.area_id IN (SELECT id FROM cities)
    ),
    aggs AS (
      SELECT
        area_id,
        count(*)::int                                              AS history_months,
        max(period_end)                                            AS latest_period_end,
        max(sale_to_list_ratio) FILTER (WHERE rn = 1)              AS s2l_1m,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY sale_to_list_ratio)
          FILTER (WHERE rn <= 3)                                   AS s2l_3m
      FROM ranked
      GROUP BY area_id
    ),
    latest AS (
      SELECT
        area_id,
        median_dom,
        active_listings,
        sample_size,
        confidence_score,
        median_sale_price,
        months_of_supply,
        pct_with_price_drops
      FROM ranked WHERE rn = 1
    )
    SELECT
      cities.slug,
      cities.name,
      cities.county_name,
      coalesce(aggs.history_months, 0)         AS history_months,
      aggs.latest_period_end                    AS latest_period_end,
      latest.median_dom                         AS median_dom,
      latest.active_listings                    AS active_listings,
      latest.sample_size                        AS sample_size,
      latest.confidence_score                   AS confidence_score,
      latest.median_sale_price::text            AS median_sale_price,
      latest.months_of_supply::text             AS months_of_supply,
      latest.pct_with_price_drops::text         AS pct_with_price_drops,
      aggs.s2l_1m::text                         AS s2l_1m,
      aggs.s2l_3m::text                         AS s2l_3m
    FROM cities
    LEFT JOIN aggs   ON aggs.area_id   = cities.id
    LEFT JOIN latest ON latest.area_id = cities.id
    ORDER BY cities.name;
  `;
  return rows;
}

/** Most-recent market_snapshot for a city. Property type = 'sfh' for now
 * (the Phase 0 ingest writes `All Residential` rollups under that key —
 * see packages/etl/load_snapshots.py for the TODO to split this when the
 * SFH/condo split lands). */
export async function getLatestCitySnapshot(
  citySlug: string,
): Promise<CitySnapshotRow | null> {
  const rows = await getSql()<CitySnapshotRow[]>`
    SELECT
      ms.period_kind::text         AS period_kind,
      ms.period_start              AS period_start,
      ms.period_end                AS period_end,
      ms.median_sale_price::text   AS median_sale_price,
      ms.median_ppsf::text         AS median_ppsf,
      ms.median_dom                AS median_dom,
      ms.sale_to_list_ratio::text  AS sale_to_list_ratio,
      ms.homes_sold                AS homes_sold,
      ms.active_listings           AS active_listings,
      ms.new_listings              AS new_listings,
      ms.months_of_supply::text    AS months_of_supply,
      ms.pct_with_price_drops::text AS pct_with_price_drops,
      ms.sample_size               AS sample_size,
      ms.confidence_score          AS confidence_score,
      ms.computed_at               AS computed_at,
      ms.source_versions           AS source_versions
    FROM market_snapshot ms
    JOIN geographic_area city ON ms.area_id = city.id
    WHERE city.slug = ${citySlug}
      AND city.kind = 'city'
      AND ms.property_type = 'sfh'
    ORDER BY ms.period_start DESC
    LIMIT 1;
  `;
  return rows[0] ?? null;
}

export type MetroSummary = {
  slug: string;
  name: string;
  total_areas: number;
  total_cities: number;
  total_counties: number;
};

/**
 * Summary card for a metro page header.
 */
export async function getMetroSummary(metroSlug: string): Promise<MetroSummary | null> {
  const rows = await getSql()<MetroSummary[]>`
    SELECT
      m.slug                                                         AS slug,
      m.name                                                         AS name,
      (SELECT count(*)::int FROM geographic_area WHERE metro_id = m.id) AS total_areas,
      (SELECT count(*)::int FROM geographic_area WHERE metro_id = m.id AND kind = 'city')   AS total_cities,
      (SELECT count(*)::int FROM geographic_area WHERE metro_id = m.id AND kind = 'county') AS total_counties
    FROM geographic_area m
    WHERE m.slug = ${metroSlug} AND m.kind = 'metro';
  `;
  return rows[0] ?? null;
}
