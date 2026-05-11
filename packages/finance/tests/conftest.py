"""Pytest config for ``bayre-finance``.

The package's modules live flat under ``packages/finance/`` (per
``docs/contracts.md`` C3 and ``docs/design.md`` §2). To import them
during testing without first installing the wheel, we add the parent
of ``packages/finance/`` (i.e., the repo's ``packages/``) to
``sys.path`` so ``import finance.affordability`` resolves.

This is dev-time only; CI's ``uv sync`` installs the wheel and the
import would resolve via the installed distribution either way.
"""

from __future__ import annotations

import sys
from pathlib import Path

_FINANCE_DIR = Path(__file__).resolve().parent.parent
_PACKAGES_DIR = _FINANCE_DIR.parent

# Insert at index 0 so our local source wins over any stale installed
# version of the wheel.
for path in (str(_PACKAGES_DIR), str(_FINANCE_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)
