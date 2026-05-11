"""
Bay Area Housing Dashboard Generator
Reads all data/YYYY-MM.json files and generates dashboard/index.html
"""

import json
import sys
from pathlib import Path
from datetime import datetime

DATA_DIR  = Path(__file__).parent.parent / "data"
DASH_DIR  = Path(__file__).parent.parent / "dashboard"
DASH_DIR.mkdir(exist_ok=True)


# ── Load all monthly snapshots ─────────────────────────────────────────────────

def load_all_months() -> list[dict]:
    files = sorted(DATA_DIR.glob("????-??.json"))
    months = []
    for f in files:
        try:
            months.append(json.loads(f.read_text()))
        except Exception as e:
            print(f"Warning: could not load {f}: {e}", file=sys.stderr)
    return months


def city_names(months: list[dict]) -> list[str]:
    if not months:
        return []
    return [c["city"] for c in months[-1]["cities"]]


def series_for_city(months: list[dict], city: str, field: str, section: str = "sfh"):
    """Extract a time-series list of (month_label, value) for one metric."""
    out = []
    for m in months:
        val = None
        for c in m["cities"]:
            if c["city"] == city:
                val = c.get(section, {}).get(field)
                break
        out.append({"month": m["month"], "value": val})
    return out


# ── HTML template ──────────────────────────────────────────────────────────────

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bay Area Housing Tracker</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg:#0a0a0a; --surface:#131313; --card:#181818;
    --border:#252525; --border2:#1e1e1e;
    --tx:#e4e0d8; --tx2:#7a7570; --tx3:#3d3a36;
    --green:#4ade80; --red:#f87171; --amber:#fbbf24;
    --blue:#60a5fa; --purple:#a78bfa;
    --alameda:#34d399; --sc:#818cf8;
  }
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:var(--bg);color:var(--tx);font-family:'DM Mono',ui-monospace,monospace;font-size:13px;min-height:100vh}

  /* ── Nav ── */
  nav{background:var(--surface);border-bottom:1px solid var(--border);padding:14px 28px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
  nav h1{font-size:15px;font-weight:500;letter-spacing:.02em;color:var(--tx)}
  nav h1 span{color:var(--tx2);font-weight:400}
  .nav-meta{font-size:11px;color:var(--tx2)}

  /* ── Layout ── */
  .wrap{max-width:1400px;margin:0 auto;padding:28px 24px 60px}

  /* ── Controls ── */
  .controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin-bottom:28px}
  .control-group{display:flex;align-items:center;gap:8px}
  label{font-size:11px;color:var(--tx2);letter-spacing:.05em;text-transform:uppercase}
  select,button{background:var(--surface);color:var(--tx);border:1px solid var(--border);border-radius:5px;padding:6px 12px;font-size:12px;font-family:inherit;cursor:pointer;transition:border-color .15s}
  select:hover,button:hover{border-color:#444}
  button.active{border-color:var(--amber);color:var(--amber)}

  /* ── Summary cards ── */
  .summary-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin-bottom:28px}
  .card{background:var(--card);border:1px solid var(--border2);border-radius:8px;padding:14px 16px}
  .card .city-label{font-size:10px;color:var(--tx2);letter-spacing:.06em;text-transform:uppercase;margin-bottom:4px}
  .card .county-tag{font-size:9px;letter-spacing:.05em;padding:1px 6px;border-radius:3px;margin-left:6px}
  .tag-a{color:var(--alameda);background:rgba(52,211,153,.08);border:1px solid rgba(52,211,153,.18)}
  .tag-s{color:var(--sc);background:rgba(129,140,248,.08);border:1px solid rgba(129,140,248,.18)}
  .card .sfh-price{font-size:18px;font-weight:500;color:var(--tx);margin:6px 0 3px}
  .card .yoy{font-size:11px}
  .up{color:var(--green)} .dn{color:var(--red)} .flat{color:var(--amber)}
  .card .condo-row{margin-top:8px;padding-top:8px;border-top:1px solid var(--border2);font-size:11px;color:var(--tx2)}
  .card .dom-row{margin-top:4px;font-size:11px;color:var(--tx2)}
  .card .ratio-row{font-size:11px;color:var(--tx2)}

  /* ── Charts section ── */
  .section-title{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--tx3);margin:28px 0 14px;padding-bottom:6px;border-bottom:1px solid var(--border2)}
  .chart-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:18px;margin-bottom:28px}
  .chart-card{background:var(--card);border:1px solid var(--border2);border-radius:8px;padding:16px}
  .chart-card h3{font-size:12px;font-weight:500;color:var(--tx);margin-bottom:12px}
  .chart-card h3 span{font-weight:400;color:var(--tx2);font-size:11px}
  .chart-wrap{position:relative;height:200px}

  /* ── Table ── */
  .table-wrap{overflow-x:auto;border:1px solid var(--border);border-radius:8px;margin-bottom:28px}
  table{width:100%;border-collapse:collapse;min-width:900px}
  thead{background:var(--surface)}
  th{padding:9px 13px;text-align:left;font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--tx3);white-space:nowrap;border-bottom:1px solid var(--border)}
  td{padding:9px 13px;border-bottom:1px solid var(--border2);vertical-align:middle;white-space:nowrap}
  tr:last-child td{border-bottom:none}
  tr:hover td{background:rgba(255,255,255,.015)}
  .type-sfh{color:var(--amber);background:rgba(251,191,36,.07);border:1px solid rgba(251,191,36,.18);font-size:9px;padding:2px 7px;border-radius:3px;letter-spacing:.05em;text-transform:uppercase}
  .type-condo{color:#94a3b8;background:rgba(148,163,184,.06);border:1px solid rgba(148,163,184,.15);font-size:9px;padding:2px 7px;border-radius:3px;letter-spacing:.05em;text-transform:uppercase}
  .city-name-cell{font-weight:500;color:var(--tx)}

  /* ── Footer ── */
  footer{font-size:10px;color:var(--tx3);line-height:1.7;padding-top:20px;border-top:1px solid var(--border2)}
  footer a{color:var(--tx2);text-decoration:none;border-bottom:1px solid var(--border)}
</style>
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
</head>
<body>

<nav>
  <h1>Bay Area Housing Tracker <span>· SFH vs Condo</span></h1>
  <div class="nav-meta">Last updated: <strong id="last-updated">—</strong> &nbsp;|&nbsp; <span id="month-count">—</span> months of data</div>
</nav>

<div class="wrap">

  <div class="controls">
    <div class="control-group">
      <label>Month</label>
      <select id="month-select"></select>
    </div>
    <div class="control-group">
      <label>County</label>
      <button id="btn-all" class="active" onclick="filterCounty('all')">All</button>
      <button id="btn-alameda" onclick="filterCounty('Alameda')">Alameda</button>
      <button id="btn-sc" onclick="filterCounty('Santa Clara')">Santa Clara</button>
    </div>
  </div>

  <!-- Summary cards -->
  <div class="summary-grid" id="summary-grid"></div>

  <!-- Trend charts -->
  <div class="section-title">SFH median price trends</div>
  <div class="chart-grid" id="chart-grid"></div>

  <!-- Detail table -->
  <div class="section-title">Full data table</div>
  <div class="table-wrap">
    <table id="detail-table">
      <thead>
        <tr>
          <th>City</th><th>County</th><th>Type</th>
          <th>Median Price</th><th>YoY %</th>
          <th>Days on Market</th><th>Sale-to-List</th>
          <th>Homes Sold</th><th>Zillow ZHVI</th>
        </tr>
      </thead>
      <tbody id="table-body"></tbody>
    </table>
  </div>

  <footer id="footer"></footer>
</div>

<script>
// ── Embedded data ────────────────────────────────────────────────────────────
const ALL_DATA = __ALL_DATA__;

// ── State ────────────────────────────────────────────────────────────────────
let selectedMonth = null;
let countyFilter = 'all';
let chartInstances = {};

// ── Init ─────────────────────────────────────────────────────────────────────
function init() {
  if (!ALL_DATA.length) {
    document.getElementById('summary-grid').innerHTML =
      '<p style="color:var(--tx2);padding:20px">No data yet. Run <code>python scripts/scrape.py</code> to fetch the first month.</p>';
    return;
  }

  const months = ALL_DATA.map(d => d.month).sort();
  selectedMonth = months[months.length - 1];

  document.getElementById('last-updated').textContent =
    ALL_DATA[ALL_DATA.length - 1].scraped_at
      ? new Date(ALL_DATA[ALL_DATA.length - 1].scraped_at).toLocaleDateString('en-US', {month:'short',day:'numeric',year:'numeric'})
      : selectedMonth;
  document.getElementById('month-count').textContent = months.length;

  // Populate month selector
  const sel = document.getElementById('month-select');
  months.slice().reverse().forEach(m => {
    const opt = document.createElement('option');
    opt.value = m;
    opt.textContent = formatMonth(m);
    sel.appendChild(opt);
  });
  sel.value = selectedMonth;
  sel.addEventListener('change', e => { selectedMonth = e.target.value; render(); });

  buildCharts();
  render();
}

// ── Render ───────────────────────────────────────────────────────────────────
function render() {
  const snapshot = ALL_DATA.find(d => d.month === selectedMonth);
  if (!snapshot) return;

  const cities = snapshot.cities.filter(c =>
    countyFilter === 'all' || c.county === countyFilter
  );

  renderCards(cities);
  renderTable(cities);
  renderFooter(snapshot);
}

function formatMonth(m) {
  const [y, mo] = m.split('-');
  return new Date(+y, +mo - 1, 1).toLocaleDateString('en-US', {month:'long', year:'numeric'});
}

function fmtPrice(v) {
  if (v == null) return '—';
  if (v >= 1_000_000) return '$' + (v / 1_000_000).toFixed(2) + 'M';
  if (v >= 1_000)     return '$' + Math.round(v / 1_000) + 'K';
  return '$' + v;
}

function fmtYoy(v) {
  if (v == null) return {text:'—', cls:''};
  const cls = v > 0.5 ? 'up' : v < -0.5 ? 'dn' : 'flat';
  const sign = v > 0 ? '▲ ' : v < 0 ? '▼ ' : '';
  return {text: sign + Math.abs(v).toFixed(1) + '%', cls};
}

// ── Cards ────────────────────────────────────────────────────────────────────
function renderCards(cities) {
  const grid = document.getElementById('summary-grid');
  grid.innerHTML = '';
  cities.forEach(c => {
    const yoy = fmtYoy(c.sfh.yoy_pct);
    const tagCls = c.county === 'Alameda' ? 'tag-a' : 'tag-s';
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <div class="city-label">${c.city} <span class="county-tag ${tagCls}">${c.county}</span></div>
      <div class="sfh-price">${fmtPrice(c.sfh.median_price)}</div>
      <div class="yoy ${yoy.cls}">${yoy.text} YoY (SFH)</div>
      <div class="condo-row">Condo ~${fmtPrice(c.condo.median_price_approx)}</div>
      <div class="dom-row">SFH DOM: ${c.sfh.dom ?? '—'} days</div>
    `;
    grid.appendChild(card);
  });
}

// ── Table ────────────────────────────────────────────────────────────────────
function renderTable(cities) {
  const tbody = document.getElementById('table-body');
  tbody.innerHTML = '';
  cities.forEach(c => {
    const yoy = fmtYoy(c.sfh.yoy_pct);
    const tagCls = c.county === 'Alameda' ? 'tag-a' : 'tag-s';

    // SFH row
    const sfhRow = document.createElement('tr');
    sfhRow.innerHTML = `
      <td class="city-name-cell">${c.city}</td>
      <td><span class="county-tag ${tagCls}">${c.county}</span></td>
      <td><span class="type-sfh">SFH</span></td>
      <td>${fmtPrice(c.sfh.median_price)}</td>
      <td class="${yoy.cls}">${yoy.text}</td>
      <td>${c.sfh.dom ?? '—'} days</td>
      <td>—</td>
      <td>${c.sfh.homes_sold ?? '—'}</td>
      <td>${fmtPrice(c.sfh.zillow_zhvi)}</td>
    `;
    tbody.appendChild(sfhRow);

    // Condo row
    const condoRow = document.createElement('tr');
    condoRow.innerHTML = `
      <td class="city-name-cell" style="color:var(--tx2)"></td>
      <td></td>
      <td><span class="type-condo">Condo</span></td>
      <td>${fmtPrice(c.condo.median_price_approx)} <span style="color:var(--tx3);font-size:10px">~est</span></td>
      <td style="color:var(--tx2)">—</td>
      <td>${c.condo.dom_approx ?? '—'} days <span style="color:var(--tx3);font-size:10px">~est</span></td>
      <td>${c.condo.sale_to_list_approx != null ? c.condo.sale_to_list_approx.toFixed(1) + '%' : '—'} <span style="color:var(--tx3);font-size:10px">~est</span></td>
      <td>—</td>
      <td>—</td>
    `;
    tbody.appendChild(condoRow);
  });
}

// ── Charts ────────────────────────────────────────────────────────────────────
const CITY_COLORS = {
  'Dublin':        '#34d399',
  'Pleasanton':    '#6ee7b7',
  'Fremont':       '#a7f3d0',
  'Milpitas':      '#818cf8',
  'Sunnyvale':     '#a5b4fc',
  'Mountain View': '#c4b5fd',
  'Campbell':      '#e879f9',
};

function buildCharts() {
  const grid = document.getElementById('chart-grid');
  grid.innerHTML = '';

  // One chart per city showing SFH price trend over months
  const allCities = ALL_DATA.length ? ALL_DATA[0].cities.map(c => c.city) : [];
  const monthLabels = ALL_DATA.map(d => {
    const [y, mo] = d.month.split('-');
    return new Date(+y, +mo - 1, 1).toLocaleDateString('en-US', {month:'short', year:'2-digit'});
  });

  // Also make one combined chart
  buildCombinedChart(grid, monthLabels, allCities);

  // Per-city charts
  allCities.forEach(city => {
    buildCityChart(grid, city, monthLabels);
  });
}

function buildCombinedChart(grid, monthLabels, allCities) {
  const wrap = document.createElement('div');
  wrap.className = 'chart-card';
  wrap.style.gridColumn = '1 / -1';
  wrap.innerHTML = `<h3>All cities — SFH median price <span>(combined)</span></h3><div class="chart-wrap" style="height:240px"><canvas id="chart-combined" role="img" aria-label="SFH price trends for all cities"></canvas></div>`;
  grid.appendChild(wrap);

  const datasets = allCities.map(city => {
    const prices = ALL_DATA.map(m => {
      const c = m.cities.find(x => x.city === city);
      return c?.sfh?.median_price ? c.sfh.median_price / 1_000_000 : null;
    });
    return {
      label: city,
      data: prices,
      borderColor: CITY_COLORS[city] || '#888',
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      pointRadius: 3,
      tension: 0.3,
      spanGaps: true,
    };
  });

  new Chart(document.getElementById('chart-combined'), {
    type: 'line',
    data: { labels: monthLabels.length ? monthLabels : ['No data'], datasets },
    options: chartOptions('$M'),
  });
}

function buildCityChart(grid, city, monthLabels) {
  const sfhPrices = ALL_DATA.map(m => {
    const c = m.cities.find(x => x.city === city);
    return c?.sfh?.median_price ? c.sfh.median_price / 1_000_000 : null;
  });
  const condoPrices = ALL_DATA.map(m => {
    const c = m.cities.find(x => x.city === city);
    return c?.condo?.median_price_approx ? c.condo.median_price_approx / 1_000_000 : null;
  });
  const domData = ALL_DATA.map(m => {
    const c = m.cities.find(x => x.city === city);
    return c?.sfh?.dom ?? null;
  });

  const id = 'chart-' + city.replace(/\s+/g, '-');
  const wrap = document.createElement('div');
  wrap.className = 'chart-card';
  wrap.innerHTML = `<h3>${city} <span>· price & DOM</span></h3><div class="chart-wrap"><canvas id="${id}" role="img" aria-label="${city} SFH vs condo price trend"></canvas></div>`;
  grid.appendChild(wrap);

  new Chart(document.getElementById(id), {
    type: 'line',
    data: {
      labels: monthLabels.length ? monthLabels : ['No data'],
      datasets: [
        {
          label: 'SFH ($M)',
          data: sfhPrices,
          borderColor: CITY_COLORS[city] || '#60a5fa',
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 3,
          tension: 0.3,
          spanGaps: true,
          yAxisID: 'y',
        },
        {
          label: 'Condo ($M)',
          data: condoPrices,
          borderColor: '#555',
          borderDash: [4, 3],
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          pointRadius: 2,
          tension: 0.3,
          spanGaps: true,
          yAxisID: 'y',
        },
        {
          label: 'DOM (days)',
          data: domData,
          borderColor: '#f59e0b',
          borderDash: [2, 4],
          backgroundColor: 'transparent',
          borderWidth: 1,
          pointRadius: 2,
          tension: 0.3,
          spanGaps: true,
          yAxisID: 'y2',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          labels: { color: '#7a7570', font: { size: 10, family: 'DM Mono' }, boxWidth: 12, padding: 10 },
        },
        tooltip: {
          backgroundColor: '#1a1a1a',
          borderColor: '#333',
          borderWidth: 1,
          titleColor: '#e4e0d8',
          bodyColor: '#7a7570',
          bodyFont: { family: 'DM Mono', size: 11 },
        },
      },
      scales: {
        x: {
          ticks: { color: '#4a4540', font: { size: 10 }, maxRotation: 45 },
          grid: { color: '#1a1a1a' },
        },
        y: {
          position: 'left',
          ticks: {
            color: '#4a4540',
            font: { size: 10 },
            callback: v => '$' + v.toFixed(1) + 'M',
          },
          grid: { color: '#1a1a1a' },
        },
        y2: {
          position: 'right',
          ticks: {
            color: '#4a4540',
            font: { size: 10 },
            callback: v => v + 'd',
          },
          grid: { display: false },
        },
      },
    },
  });
}

function chartOptions(unit) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        display: true,
        labels: { color: '#7a7570', font: { size: 10, family: 'DM Mono' }, boxWidth: 10, padding: 12 },
      },
      tooltip: {
        backgroundColor: '#1a1a1a',
        borderColor: '#333',
        borderWidth: 1,
        titleColor: '#e4e0d8',
        bodyColor: '#7a7570',
        callbacks: { label: ctx => ctx.dataset.label + ': $' + (ctx.parsed.y ?? 0).toFixed(2) + 'M' },
      },
    },
    scales: {
      x: {
        ticks: { color: '#4a4540', font: { size: 10 }, maxRotation: 45 },
        grid: { color: '#1a1a1a' },
      },
      y: {
        ticks: {
          color: '#4a4540',
          font: { size: 10 },
          callback: v => '$' + v.toFixed(1) + 'M',
        },
        grid: { color: '#1a1a1a' },
      },
    },
  };
}

// ── Footer ───────────────────────────────────────────────────────────────────
function renderFooter(snapshot) {
  const urls = [];
  snapshot.cities.forEach(c => {
    if (c.sources?.redfin_url) urls.push(`<a href="${c.sources.redfin_url}" target="_blank">Redfin · ${c.city}</a>`);
  });
  document.getElementById('footer').innerHTML =
    '<strong>Sources:</strong> ' + urls.join(' &nbsp;·&nbsp; ') +
    '<br>SFH figures from Redfin city housing-market pages. Condo figures marked ~est are seeded from March 2026 baseline; update via data/overrides.json.' +
    '<br>This dashboard is auto-generated. Run <code>python scripts/generate_dashboard.py</code> after scraping to refresh.';
}

// ── County filter ────────────────────────────────────────────────────────────
function filterCounty(county) {
  countyFilter = county;
  ['all','alameda','sc'].forEach(id => document.getElementById('btn-' + id).classList.remove('active'));
  const btnId = county === 'all' ? 'btn-all' : county === 'Alameda' ? 'btn-alameda' : 'btn-sc';
  document.getElementById(btnId).classList.add('active');
  render();
}

init();
</script>
</body>
</html>
"""


# ── Generate ───────────────────────────────────────────────────────────────────

def generate(months: list[dict]) -> None:
    data_json = json.dumps(months, indent=None)
    html = TEMPLATE.replace("__ALL_DATA__", data_json)
    out = DASH_DIR / "index.html"
    out.write_text(html, encoding="utf-8")
    print(f"Dashboard written → {out}")
    print(f"  Months embedded: {len(months)}")
    if months:
        cities = months[-1]["cities"]
        print(f"  Cities: {', '.join(c['city'] for c in cities)}")


def main():
    months = load_all_months()
    if not months:
        print("No data files found in data/. Generating empty-state dashboard.")
    generate(months)


if __name__ == "__main__":
    main()
