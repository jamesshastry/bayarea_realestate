"""Status-page generator (Phase 0 stub for NF-DAT-08).

Reads `data/sources.json` (schema below) and writes `status/index.html` — a
single static file fit for GitHub Pages serving.

`data/sources.json` schema (informally; the Pydantic models below are the
canonical version):

    {
      "schema_version": 1,
      "sources": {
        "<source_name>": {
          "name": "redfin_csv",
          "last_run_at": "2026-05-14T18:00:00+00:00",
          "status": "ok" | "partial" | "error",
          "successful_areas": ["fremont", ...],
          "failed_areas": {"sunnyvale": "ParseError: ..."},
          "snapshot_file": "data/2026-05-14.json" | null,
          "freshness_tier": "weekly",
          "license": "attribution"
        },
        ...
      }
    }

Phase 2 replaces this entirely with `/v1/status` (FastAPI). Until then, the
weekly GitHub Actions cron regenerates this page after every successful
ingest.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCES_PATH = REPO_ROOT / "data" / "sources.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "status" / "index.html"

# Health-state thresholds (NF-DAT-06 SLA per tier). Per-tier numbers are
# generous Phase 0 stubs; Phase 2 tightens.
_TIER_STALE_HOURS: dict[str, int] = {
    "realtime": 1,
    "near_realtime": 6,
    "daily": 36,
    "weekly": 8 * 24,  # alert if no commit in 8 days (per implementation-plan risks)
    "monthly": 35 * 24,
    "quarterly": 100 * 24,
    "annual": 380 * 24,
}


# ── Pydantic models for sources.json ────────────────────────────────────────


SourceStatusKind = Literal["ok", "partial", "error"]


class SourceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    last_run_at: datetime
    status: SourceStatusKind
    successful_areas: list[str] = []
    failed_areas: dict[str, str] = {}
    snapshot_file: str | None = None
    freshness_tier: str
    license: str


class SourcesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Annotated[int, Field(ge=1)] = 1
    sources: dict[str, SourceStatus] = {}


# ── HTML rendering ──────────────────────────────────────────────────────────


def _staleness_state(source: SourceStatus, now: datetime) -> tuple[str, str]:
    """Return ('green'|'amber'|'red', explanation) based on tier + status + age."""
    age_hours = (now - source.last_run_at).total_seconds() / 3600
    stale_after = _TIER_STALE_HOURS.get(source.freshness_tier, 24 * 14)
    if source.status == "error":
        return "red", f"Last run failed ({age_hours:.1f}h ago)."
    if age_hours > stale_after:
        return (
            "red",
            f"No successful run in {age_hours:.1f}h (tier SLA: {stale_after}h).",
        )
    if source.status == "partial" or age_hours > stale_after * 0.75:
        return "amber", (
            f"Partial / aging ({age_hours:.1f}h ago, {len(source.failed_areas)} area(s) failed)."
        )
    return (
        "green",
        f"Healthy ({age_hours:.1f}h ago, {len(source.successful_areas)} area(s) ok).",
    )


def _row_html(source: SourceStatus, now: datetime) -> str:
    state, note = _staleness_state(source, now)
    failed_li = "".join(
        f"<li><code>{html.escape(slug)}</code>: {html.escape(reason)}</li>"
        for slug, reason in sorted(source.failed_areas.items())
    )
    failed_block = (
        f"<details><summary>{len(source.failed_areas)} failed area(s)</summary>"
        f"<ul>{failed_li}</ul></details>"
        if source.failed_areas
        else ""
    )
    snapshot_link = (
        f'<a href="../{html.escape(source.snapshot_file)}">{html.escape(source.snapshot_file)}</a>'
        if source.snapshot_file
        else "<em>none</em>"
    )
    return f"""
    <tr class="state-{state}">
      <td><span class="dot dot-{state}" aria-label="{state}"></span></td>
      <td><code>{html.escape(source.name)}</code></td>
      <td>{html.escape(source.freshness_tier)}</td>
      <td>{html.escape(source.last_run_at.isoformat())}</td>
      <td>{len(source.successful_areas)}</td>
      <td>{failed_block or "&mdash;"}</td>
      <td>{snapshot_link}</td>
      <td>{html.escape(source.license)}</td>
      <td>{html.escape(note)}</td>
    </tr>
    """


_CSS = """
:root {
  color-scheme: dark;
  --bg: oklch(15% 0 0);
  --surface: oklch(19% 0 0);
  --border: oklch(28% 0 0);
  --tx: oklch(90% 0.02 80);
  --tx-muted: oklch(60% 0.02 80);
  --green: oklch(75% 0.18 145);
  --amber: oklch(82% 0.16 75);
  --red: oklch(70% 0.21 25);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font: 14px/1.5 -apple-system, "SF Pro Text", "Segoe UI", system-ui, sans-serif;
  color: var(--tx);
  background: var(--bg);
  padding: 32px;
}
h1 { margin: 0 0 8px; font-weight: 600; letter-spacing: -0.01em; }
.sub { color: var(--tx-muted); margin: 0 0 24px; }
table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
th, td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}
th {
  background: oklch(22% 0 0);
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--tx-muted);
}
tr:last-child td { border-bottom: 0; }
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.dot-green { background: var(--green); box-shadow: 0 0 8px var(--green); }
.dot-amber { background: var(--amber); box-shadow: 0 0 8px var(--amber); }
.dot-red { background: var(--red); box-shadow: 0 0 8px var(--red); }
code { font: 12px/1.4 ui-monospace, "SF Mono", Menlo, monospace; color: var(--tx); }
details > summary { cursor: pointer; color: var(--tx-muted); }
ul { margin: 8px 0 0 20px; padding: 0; }
.footer { margin-top: 24px; color: var(--tx-muted); font-size: 12px; }
.empty { padding: 40px; text-align: center; color: var(--tx-muted); }
"""


def render_status_page(sources_file: SourcesFile, *, now: datetime | None = None) -> str:
    """Pure render — given a parsed sources file, return the full HTML string."""
    now = now or datetime.now(tz=UTC)
    if not sources_file.sources:
        body = '<div class="empty">No sources have run yet.</div>'
    else:
        rows = "".join(_row_html(s, now) for _, s in sorted(sources_file.sources.items()))
        body = f"""
        <table>
          <thead>
            <tr>
              <th></th><th>Source</th><th>Tier</th><th>Last run (UTC)</th>
              <th>OK</th><th>Failed</th><th>Snapshot file</th>
              <th>License</th><th>Notes</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
        """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bay Area FTHB · Data status</title>
  <meta name="generator" content="packages.observability.status_page">
  <style>{_CSS}</style>
</head>
<body>
  <h1>Data status</h1>
  <p class="sub">
    Per-source ingest health for the Bay Area FTHB pipeline.
    Phase 0 stub — Phase 2 replaces this with <code>/v1/status</code>.
    Generated {html.escape(now.isoformat())}.
  </p>
  {body}
  <p class="footer">
    Sources file: <code>data/sources.json</code>.
    Stale-thresholds per freshness tier per <code>NF-DAT-06</code>.
  </p>
</body>
</html>
"""


def generate_status_html(
    sources_path: Path = DEFAULT_SOURCES_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    *,
    now: datetime | None = None,
) -> Path:
    """Read sources.json (or default to an empty file), render, and write."""
    if sources_path.exists():
        payload = json.loads(sources_path.read_text(encoding="utf-8"))
        sources_file = SourcesFile.model_validate(payload)
    else:
        sources_file = SourcesFile()
    html_text = render_status_page(sources_file, now=now)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")
    return output_path


# ── CLI ─────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="packages.observability.status_page",
        description="Generate the Phase 0 static status page from data/sources.json.",
    )
    p.add_argument("--sources", type=Path, default=DEFAULT_SOURCES_PATH)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = generate_status_html(sources_path=args.sources, output_path=args.output)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
