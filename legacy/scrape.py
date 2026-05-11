"""
Bay Area Housing Market Scraper
Fetches SFH vs Condo stats for 7 cities from Redfin, Zillow, and Movoto.
Saves monthly snapshots to data/YYYY-MM.json
"""

import json
import time
import random
import logging
import argparse
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ── City config ────────────────────────────────────────────────────────────────

CITIES = [
    {
        "name": "Dublin",
        "county": "Alameda",
        "redfin_slug": "city/5159/CA/Dublin",
        "zillow_id": "51751",
        "movoto_slug": "dublin-ca",
    },
    {
        "name": "Pleasanton",
        "county": "Alameda",
        "redfin_slug": "city/14986/CA/Pleasanton",
        "zillow_id": "47164",
        "movoto_slug": "pleasanton-ca",
    },
    {
        "name": "Fremont",
        "county": "Alameda",
        "redfin_slug": "city/6671/CA/Fremont",
        "zillow_id": "11540",
        "movoto_slug": "fremont-ca",
    },
    {
        "name": "Milpitas",
        "county": "Santa Clara",
        "redfin_slug": "city/12204/CA/Milpitas",
        "zillow_id": "39798",
        "movoto_slug": "milpitas-ca",
    },
    {
        "name": "Sunnyvale",
        "county": "Santa Clara",
        "redfin_slug": "city/19457/CA/Sunnyvale",
        "zillow_id": "54626",
        "movoto_slug": "sunnyvale-ca",
    },
    {
        "name": "Mountain View",
        "county": "Santa Clara",
        "redfin_slug": "city/12739/CA/Mountain-View",
        "zillow_id": "54488",
        "movoto_slug": "mountain-view-ca",
    },
    {
        "name": "Campbell",
        "county": "Santa Clara",
        "redfin_slug": "city/2673/CA/Campbell",
        "zillow_id": "17272",
        "movoto_slug": "campbell-ca",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def get(url: str, retries: int = 3, delay: float = 4.0) -> requests.Response | None:
    """GET with retries and polite delays."""
    for attempt in range(1, retries + 1):
        try:
            time.sleep(delay + random.uniform(0, 2))
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                return r
            log.warning("HTTP %s on %s (attempt %d)", r.status_code, url, attempt)
        except requests.RequestException as exc:
            log.warning("Request error on %s: %s (attempt %d)", url, exc, attempt)
    return None


def parse_price(text: str) -> float | None:
    """'$1.75M' → 1_750_000  |  '$956K' → 956_000  |  None on failure."""
    if not text:
        return None
    t = text.strip().replace(",", "").replace("$", "")
    try:
        if t.upper().endswith("M"):
            return float(t[:-1]) * 1_000_000
        if t.upper().endswith("K"):
            return float(t[:-1]) * 1_000
        return float(t)
    except ValueError:
        return None


def parse_pct(text: str) -> float | None:
    """'-7.9%' → -7.9  |  None on failure."""
    if not text:
        return None
    t = text.strip().replace("%", "").replace("+", "")
    try:
        return float(t)
    except ValueError:
        return None


# ── Redfin scraper ─────────────────────────────────────────────────────────────

def scrape_redfin(city: dict) -> dict:
    """
    Scrapes Redfin housing-market page for a city.
    Returns a dict with keys: median_price, yoy_pct, dom, ppsf, homes_sold.
    All values may be None if parsing fails.
    """
    url = f"https://www.redfin.com/{city['redfin_slug']}/housing-market"
    log.info("Redfin → %s", url)
    r = get(url)
    if not r:
        return {}

    soup = BeautifulSoup(r.text, "html.parser")
    result: dict = {}

    # Redfin embeds JSON-LD + a server-side data blob.  We look for the
    # primary stat table that contains "Median sale price", "Days on market", etc.
    # Because Redfin is a React SPA the static HTML includes a <script> block
    # with a "window.__reactInitialProps__" or similar; we do best-effort text
    # extraction from visible stat elements.

    # Try to find stat blocks (class names vary by page version)
    stat_blocks = soup.find_all(
        lambda tag: tag.name in ("div", "span")
        and tag.get_text(strip=True).startswith("$")
        and "M" in tag.get_text(strip=True),
    )

    # Look for median price in meta tags / og:description as a fallback
    og_desc = soup.find("meta", property="og:description")
    if og_desc and og_desc.get("content"):
        desc = og_desc["content"]
        # e.g. "median sale price of a home in Fremont was $1.5M last month, down 8.0%"
        import re
        price_match = re.search(r"\$([0-9.]+[MK])", desc)
        yoy_match = re.search(r"(up|down)\s+([0-9.]+)%", desc, re.IGNORECASE)
        dom_match = re.search(r"sell after\s+(\d+)\s+days", desc)

        if price_match:
            result["median_price"] = parse_price("$" + price_match.group(1))
        if yoy_match:
            sign = -1 if yoy_match.group(1).lower() == "down" else 1
            result["yoy_pct"] = sign * float(yoy_match.group(2))
        if dom_match:
            result["dom"] = int(dom_match.group(1))

    # Scrape page title for city confirmation
    title = soup.find("title")
    if title:
        result["source_title"] = title.get_text(strip=True)

    result["source"] = "redfin"
    result["url"] = url
    return result


# ── Zillow scraper ─────────────────────────────────────────────────────────────

def scrape_zillow(city: dict) -> dict:
    """
    Fetches Zillow home-values page.
    Zillow's pages are React-rendered; we extract from meta/og tags.
    """
    url = f"https://www.zillow.com/home-values/{city['zillow_id']}/{city['movoto_slug']}/"
    log.info("Zillow  → %s", url)
    r = get(url, delay=5)
    if not r:
        return {}

    import re
    soup = BeautifulSoup(r.text, "html.parser")
    result: dict = {"source": "zillow", "url": url}

    # Zillow embeds data in <script type="application/json"> blocks
    scripts = soup.find_all("script", type="application/json")
    for s in scripts:
        text = s.get_text()
        # Look for zhvi / typical home value patterns
        m = re.search(r'"homeValueForecast"\s*:\s*\{[^}]*"value"\s*:\s*([0-9.]+)', text)
        if m:
            result["zhvi"] = float(m.group(1))
            break
        m = re.search(r'"zhvi"\s*:\s*([0-9.]+)', text)
        if m:
            result["zhvi"] = float(m.group(1))
            break

    # Fallback: og:description
    og = soup.find("meta", property="og:description")
    if og and og.get("content"):
        desc = og["content"]
        m = re.search(r"\$([0-9,.]+)", desc)
        if m and "zhvi" not in result:
            result["zhvi"] = float(m.group(1).replace(",", ""))
        yoy = re.search(r"(up|down)\s+([0-9.]+)%", desc, re.IGNORECASE)
        if yoy:
            sign = -1 if yoy.group(1).lower() == "down" else 1
            result["yoy_pct"] = sign * float(yoy.group(2))

    return result


# ── Movoto scraper ─────────────────────────────────────────────────────────────

def scrape_movoto(city: dict) -> dict:
    """
    Scrapes Movoto market-trends page for median price, DOM, homes sold.
    Movoto serves mostly static HTML which is easier to parse.
    """
    url = f"https://www.movoto.com/{city['movoto_slug']}/market-trends/"
    log.info("Movoto  → %s", url)
    r = get(url, delay=3)
    if not r:
        return {}

    import re
    soup = BeautifulSoup(r.text, "html.parser")
    result: dict = {"source": "movoto", "url": url}

    text = soup.get_text(" ", strip=True)

    # Pattern: "homes sold for a median price of $1,498,000 in March 2026"
    price_m = re.search(r"median price of \$([\d,]+)", text)
    if price_m:
        result["median_price"] = float(price_m.group(1).replace(",", ""))

    # Pattern: "sell after 18 days on the market"
    dom_m = re.search(r"sell after (\d+) days", text)
    if dom_m:
        result["dom"] = int(dom_m.group(1))

    # Pattern: "398 homes were sold"
    sold_m = re.search(r"([\d,]+) homes were sold", text)
    if sold_m:
        result["homes_sold"] = int(sold_m.group(1).replace(",", ""))

    return result


# ── Merge & structure ──────────────────────────────────────────────────────────

MANUAL_CONDO_NOTES = {
    "Dublin":        {"condo_price_approx": 956_000,  "condo_dom_approx": 30, "condo_ratio_approx": 98.0},
    "Pleasanton":    {"condo_price_approx": 515_000,  "condo_dom_approx": 22, "condo_ratio_approx": 97.5},
    "Fremont":       {"condo_price_approx": 1_000_000,"condo_dom_approx": 25, "condo_ratio_approx": 101.0},
    "Milpitas":      {"condo_price_approx": 965_000,  "condo_dom_approx": 45, "condo_ratio_approx": 99.0},
    "Sunnyvale":     {"condo_price_approx": 1_250_000,"condo_dom_approx": 25, "condo_ratio_approx": 104.0},
    "Mountain View": {"condo_price_approx": 1_150_000,"condo_dom_approx": 40, "condo_ratio_approx": 102.0},
    "Campbell":      {"condo_price_approx": 1_000_000,"condo_dom_approx": 35, "condo_ratio_approx": 101.0},
}


def build_city_record(city: dict, redfin: dict, zillow: dict, movoto: dict) -> dict:
    """Merge scraped data into a clean record."""
    # Prefer Redfin > Movoto > Zillow for median price
    median = (
        redfin.get("median_price")
        or movoto.get("median_price")
        or zillow.get("zhvi")
    )
    yoy = redfin.get("yoy_pct") or zillow.get("yoy_pct")
    dom = redfin.get("dom") or movoto.get("dom")
    homes_sold = movoto.get("homes_sold")
    zhvi = zillow.get("zhvi")
    condo = MANUAL_CONDO_NOTES.get(city["name"], {})

    return {
        "city": city["name"],
        "county": city["county"],
        "sfh": {
            "median_price": median,
            "yoy_pct": yoy,
            "dom": dom,
            "homes_sold": homes_sold,
            "zillow_zhvi": zhvi,
        },
        "condo": {
            "median_price_approx": condo.get("condo_price_approx"),
            "dom_approx": condo.get("condo_dom_approx"),
            "sale_to_list_approx": condo.get("condo_ratio_approx"),
            "note": (
                "Condo figures are seed estimates from March 2026 baseline. "
                "Update manually from Redfin condo sub-pages or override in data/overrides.json."
            ),
        },
        "sources": {
            "redfin_url": redfin.get("url"),
            "zillow_url": zillow.get("url"),
            "movoto_url": movoto.get("url"),
        },
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Scrape Bay Area housing market data")
    parser.add_argument(
        "--month",
        default=datetime.now().strftime("%Y-%m"),
        help="Month to tag data as (YYYY-MM). Defaults to current month.",
    )
    parser.add_argument(
        "--cities",
        nargs="*",
        default=None,
        help="Subset of city names to scrape (e.g. --cities Dublin Fremont). Defaults to all.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip network requests; load existing data or use empty stubs.",
    )
    args = parser.parse_args()

    target_cities = CITIES
    if args.cities:
        names = {c.lower() for c in args.cities}
        target_cities = [c for c in CITIES if c["name"].lower() in names]
        if not target_cities:
            log.error("No matching cities found for: %s", args.cities)
            return

    log.info("Scraping %d cities for month %s", len(target_cities), args.month)

    records = []
    for city in target_cities:
        log.info("── %s ──────────────────────────────", city["name"])
        if args.dry_run:
            redfin_data, zillow_data, movoto_data = {}, {}, {}
        else:
            redfin_data = scrape_redfin(city)
            zillow_data = scrape_zillow(city)
            movoto_data = scrape_movoto(city)

        record = build_city_record(city, redfin_data, zillow_data, movoto_data)
        records.append(record)
        log.info(
            "  %s → SFH median: %s  YoY: %s%%  DOM: %s",
            city["name"],
            f"${record['sfh']['median_price']:,.0f}" if record["sfh"]["median_price"] else "n/a",
            record["sfh"]["yoy_pct"],
            record["sfh"]["dom"],
        )

    # Apply manual overrides if present
    override_path = DATA_DIR / "overrides.json"
    if override_path.exists():
        overrides = json.loads(override_path.read_text())
        month_overrides = overrides.get(args.month, {})
        for record in records:
            city_ov = month_overrides.get(record["city"], {})
            if city_ov:
                log.info("Applying overrides for %s", record["city"])
                for section in ("sfh", "condo"):
                    for k, v in city_ov.get(section, {}).items():
                        record[section][k] = v

    output = {
        "month": args.month,
        "scraped_at": datetime.utcnow().isoformat() + "Z",
        "cities": records,
    }

    out_path = DATA_DIR / f"{args.month}.json"
    out_path.write_text(json.dumps(output, indent=2))
    log.info("Saved → %s", out_path)


if __name__ == "__main__":
    main()
