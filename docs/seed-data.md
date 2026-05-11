# Seed Data Specification

> Status: Draft v1 · Owner: project lead · Last updated: 2026-05-11
> Defines the exact `GeographicArea`, `School`, `SchoolDistrict`, and `AttendanceZone` rows that must exist after Phase 0/2 ingest. This is the Bay Area baseline; other metros (Phase 5+) follow the same pattern.

---

## 1. Why this is a separate document

Three reasons a seed-data spec earns its own file rather than living in `datamodel.md`:

1. **It's the contract between ETL agents and product agents.** Agents writing API endpoints can mock against this list. Agents writing ingest code know exactly which slugs / codes / boundaries to fetch. Without it, naming conventions drift across PRs.
2. **It pins names that mislead.** "Fremont High School" is in **Sunnyvale**, not Fremont. "Foothill High School" exists in [several California cities](https://www.cde.ca.gov/SchoolDirectory/) — we mean the Pleasanton one. Without explicit CDS codes, an agent will pick the wrong school.
3. **It's the first row a future "add a metro" runbook (Phase 5) will reference.** Sacramento's seed spec will be modeled on this one.

---

## 2. Scope (Bay Area baseline)

### 2.1 Cities — the original 7

These come from `scrape.py::CITIES` and remain the primary product surface through Phase 2. (Phase 2 also onboards all ~100 Bay Area cities, but these 7 must be reachable from the metro page on day one.)

| Slug | Name | County | Notes |
|------|------|--------|-------|
| `dublin` | Dublin | Alameda | Tri-Valley; high Mello-Roos exposure in newer subdivisions |
| `pleasanton` | Pleasanton | Alameda | Tri-Valley; older housing stock |
| `fremont` | Fremont | Alameda | Largest of the 7 by population; spans 4 high school zones |
| `milpitas` | Milpitas | Santa Clara | Bay-adjacent; close to Tesla / Cisco |
| `sunnyvale` | Sunnyvale | Santa Clara | Apple / Google / LinkedIn employer base |
| `mountain-view` | Mountain View | Santa Clara | Google HQ; expensive |
| `campbell` | Campbell | Santa Clara | South Bay; smaller / quieter |

### 2.2 Counties — the 2

| Slug | Name | FIPS | Schools districts of interest |
|------|------|------|-------------------------------|
| `alameda` | Alameda County | `06001` | Dublin USD, Pleasanton USD, Fremont USD (city of Fremont) |
| `santa-clara` | Santa Clara County | `06085` | Fremont **Union** HSD (Sunnyvale + Cupertino + Los Altos), Mountain View Whisman / MVLA, Sunnyvale SD, Campbell USD, Milpitas USD |

### 2.3 Metro

| Slug | Name | Members |
|------|------|---------|
| `bay-area` | Bay Area | Alameda + Santa Clara (Phase 0–2 scope; 9-county definition expands later) |

---

## 3. Priority high schools (3)

These are the user's named priorities — they get full school pages, attendance-zone-scoped market snapshots, and school-premium calculations from Phase 3 onward.

### 3.1 Foothill High School (Pleasanton)

- **CDS code:** `01751010130096`
- **District:** Pleasanton Unified School District
- **City:** Pleasanton
- **County:** Alameda
- **CDE profile:** [cde.ca.gov/sdprofile/details.aspx?cds=01751010130096](https://www.cde.ca.gov/sdprofile/details.aspx?cds=01751010130096)
- **Slug:** `foothill-pleasanton`
- **Note:** Multiple "Foothill High Schools" exist in California (Bakersfield, Henderson NV, Santa Ana, Tustin) — pin by CDS code, never by name alone.

### 3.2 Fremont High School (Sunnyvale)

- **CDS code:** `43694684332474`
- **District:** Fremont Union High School District (FUHSD)
- **City:** Sunnyvale
- **County:** Santa Clara
- **CDE profile:** [cde.ca.gov/SchoolDirectory/details?cdscode=43694684332474](https://www.cde.ca.gov/SchoolDirectory/details?cdscode=43694684332474)
- **Slug:** `fremont-sunnyvale`
- **⚠️ Naming hazard:** This school is in **Sunnyvale**, not Fremont. The district is named for John C. Frémont, not the city. There is also a "Fremont High School" in Oakland (different CDS) and in Los Angeles. Pin everything by CDS code; never by name. URL slug includes the city to disambiguate for users.

### 3.3 Dublin High School (Dublin)

- **CDS code:** `01750930132704`
- **District:** Dublin Unified School District
- **City:** Dublin
- **County:** Alameda
- **CDE profile:** [cde.ca.gov/sdprofile/details.aspx?cds=01750930132704](https://www.cde.ca.gov/sdprofile/details.aspx?cds=01750930132704)
- **Slug:** `dublin-dublin`
- **Note:** Slug doubles up because the city name == school name — keeps URL pattern uniform with the others.

---

## 4. School districts seeded (5)

The 3 priority schools sit in 3 districts. We seed all 5 listed below because they cover all 7 priority cities and provide the comparison baseline for the school-premium calculation.

| Slug | Name | County | CDS | Notes |
|------|------|--------|-----|-------|
| `pleasanton-usd` | Pleasanton Unified School District | Alameda | (TBD via CDE district lookup) | Operates Foothill HS |
| `dublin-usd` | Dublin Unified School District | Alameda | (TBD) | Operates Dublin HS |
| `fremont-usd` | Fremont Unified School District | Alameda | (TBD) | Operates the Fremont **city** high schools (Mission San Jose HS, Irvington HS, Kennedy HS, American HS, Washington HS). NOT Fremont HS Sunnyvale. |
| `fuhsd` | Fremont Union High School District | Santa Clara | (TBD) | Operates Fremont HS Sunnyvale, plus Cupertino HS, Homestead HS, Lynbrook HS, Monta Vista HS |
| `mvla` | Mountain View – Los Altos Union HSD | Santa Clara | (TBD) | Operates Mountain View HS, Los Altos HS |

**District CDS codes are TBD** because they're a one-off lookup at ingest time — the ingest job (Phase 2 deliverable) writes them when fetching CDE district records.

---

## 5. Attendance zones (3 — one per priority school)

Three `AttendanceZone` rows + 3 `GeographicArea` rows of `kind='school_zone'` are required for the school-premium calculation (`F-GEO-04`).

| Linked school | Polygon source | Effective dates |
|---------------|----------------|-----------------|
| Foothill HS Pleasanton | Pleasanton USD official boundary publication (PDF / GIS layer); cross-reference [GreatSchools attendance map](https://www.greatschools.org) | `effective_from = 2024-08-01` (latest known boundary; revisit on official re-zone) |
| Fremont HS Sunnyvale | FUHSD boundary map (FUHSD publishes attendance boundaries on [fuhsd.org](https://www.fuhsd.org/)) | Same |
| Dublin HS Dublin | Dublin USD boundary | Same |

Phase 3 deliverable: a small per-district digitization runbook (`docs/runbooks/digitize-attendance-zone.md`) covering the QGIS / Mapbox Studio steps for converting district PDFs to GeoJSON. The 3 priority zones are the runbook's first test cases.

---

## 6. Resulting `GeographicArea` rows (the materialization)

After seeding, the `geographic_area` table contains at minimum:

```
kind='metro',           name='Bay Area',                slug='bay-area'
kind='county',          name='Alameda County',          slug='alameda'         parent=bay-area
kind='county',          name='Santa Clara County',      slug='santa-clara'     parent=bay-area
kind='city',            name='Dublin',                  slug='dublin'          parent=alameda
kind='city',            name='Pleasanton',              slug='pleasanton'      parent=alameda
kind='city',            name='Fremont',                 slug='fremont'         parent=alameda
kind='city',            name='Milpitas',                slug='milpitas'        parent=santa-clara
kind='city',            name='Sunnyvale',               slug='sunnyvale'       parent=santa-clara
kind='city',            name='Mountain View',           slug='mountain-view'   parent=santa-clara
kind='city',            name='Campbell',                slug='campbell'        parent=santa-clara
kind='school_district', name='Pleasanton USD',          slug='pleasanton-usd'  parent=alameda
kind='school_district', name='Dublin USD',              slug='dublin-usd'      parent=alameda
kind='school_district', name='Fremont USD',             slug='fremont-usd'     parent=alameda
kind='school_district', name='Fremont Union HSD',       slug='fuhsd'           parent=santa-clara
kind='school_district', name='Mountain View – Los Altos Union HSD', slug='mvla' parent=santa-clara
kind='school_zone',     name='Foothill HS attendance area',  slug='foothill-pleasanton-zone'
kind='school_zone',     name='Fremont HS (Sunnyvale) attendance area', slug='fremont-sunnyvale-zone'
kind='school_zone',     name='Dublin HS attendance area',     slug='dublin-dublin-zone'
```

All have non-null `geometry` from Census TIGER (cities, counties) or CDE / district publications (school zones / districts).

`metro_id` (denormalized) is set to the `bay-area` row's id on every member.

---

## 7. URL surface (Phase 2+)

Resulting canonical URLs after seed + Phase 2:

```
/bay-area
/bay-area/cities/dublin
/bay-area/cities/pleasanton
/bay-area/cities/fremont
/bay-area/cities/milpitas
/bay-area/cities/sunnyvale
/bay-area/cities/mountain-view
/bay-area/cities/campbell
/bay-area/schools/foothill-pleasanton
/bay-area/schools/fremont-sunnyvale
/bay-area/schools/dublin-dublin
/bay-area/timing
/bay-area/timing/fragmentation
/bay-area/compare?areas=...
/bay-area/map
```

Districts get pages at `/bay-area/districts/{slug}` from Phase 3 onward (lower priority — most users navigate via city or school, not district).

---

## 8. Phase responsibilities

| Phase | What's done with seed data |
|-------|---------------------------|
| **0** | The 7 cities are the targets of the Redfin CSV ingest. JSON snapshots include city-level data. School zones not yet ingested. |
| **2** | Full materialization in Postgres: all 18 `GeographicArea` rows above + boundaries from TIGER / CDE. The 7 cities have `MarketSnapshot` rows weekly. School-zone snapshots not yet computed (snapshots scoped to `kind='city'` only). |
| **3** | The 3 priority schools' attendance-zone polygons digitized. Snapshots computed scoped to each school zone. School pages live. School-premium calculation runs. |
| **5** | Sacramento metro added by following this doc as a template (replace cities, replace counties, replace districts). Validates F-MM-01 ("config-only" metro onboarding). |

---

## 9. Acceptance test (Phase 2 exit gate)

A reviewer can verify seed correctness with these queries against Neon:

```sql
-- 1. The metro has 2 counties, 7 cities, 5 school districts, 3 school zones
SELECT kind, count(*) FROM geographic_area
WHERE metro_id = (SELECT id FROM geographic_area WHERE slug='bay-area' AND kind='metro')
GROUP BY kind;
-- Expected: metro=1, county=2, city=7, school_district=5, school_zone=3

-- 2. Each priority school resolves by CDS code
SELECT cds_code, name, district_id FROM school
WHERE cds_code IN ('01751010130096', '43694684332474', '01750930132704')
ORDER BY cds_code;
-- Expected: 3 rows

-- 3. Every priority school has exactly one current attendance zone
SELECT s.name, count(az.id) AS current_zones
FROM school s
LEFT JOIN attendance_zone az ON az.school_id = s.id
  AND (az.effective_to IS NULL OR az.effective_to > CURRENT_DATE)
WHERE s.cds_code IN ('01751010130096', '43694684332474', '01750930132704')
GROUP BY s.id, s.name;
-- Expected: 3 rows, each with current_zones = 1
```

If any expected row count is off, ingest is incomplete — block Phase 2 close.

---

## 10. Open follow-ups

- Pull district CDS codes during Phase 2 ingest (TBD column above).
- Decide whether to include **MVLA** + **Pleasanton USD** in Phase 0 already (current 7-city ingest covers their cities, so the districts surface naturally on city pages).
- Confirm whether Foothill / Fremont (Sunnyvale) / Dublin attendance boundaries are publicly available as GeoJSON or require digitization from PDFs (affects Phase 3 effort estimate).
- Phase 5 metro onboarding: verify this doc's structure works for a metro without CDE-style districts (e.g., outside California).
