"""Regenerate `apps/api/openapi.json` from the live FastAPI app.

Run from the repo root:

    uv run python apps/api/scripts/dump_openapi.py

The frontend codegen (`apps/web/src/api/generated/`) reads from this file;
per `docs/contracts.md` C6, both the dump and the codegen run in
`make precommit` so a change to a Pydantic response model can't ship without
the corresponding TS types.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api" / "src"))

from bayre_api.main import app  # noqa: E402

if __name__ == "__main__":
    spec = app.openapi()
    out_path = REPO_ROOT / "apps" / "api" / "openapi.json"
    out_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out_path.relative_to(REPO_ROOT)} ({len(spec.get('paths', {}))} paths)")
