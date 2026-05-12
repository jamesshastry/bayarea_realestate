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
};

/**
 * List the city-kind GeographicArea rows under a metro, joined with their
 * parent county for display.
 *
 * Mirrors the SQL the future `/v1/metros/{slug}/cities` endpoint will run.
 */
export async function listCitiesInMetro(metroSlug: string): Promise<CityCard[]> {
  const rows = await getSql()<CityCard[]>`
    SELECT
      city.slug         AS slug,
      city.name         AS name,
      county.name       AS county_name,
      county.slug       AS county_slug
    FROM geographic_area city
    JOIN geographic_area county ON city.parent_id = county.id
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
