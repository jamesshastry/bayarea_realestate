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
