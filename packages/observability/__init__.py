"""bayre-observability — Phase 0: static status-page generator.

In Phase 2 this package grows to host structured logging + OTel setup
(per `docs/design.md` §10.1). Phase 0 only needs the static `/status` HTML
page (NF-DAT-08 stub).
"""

from .status_page import (
    SourcesFile,
    SourceStatus,
    generate_status_html,
    main,
    render_status_page,
)

__all__ = [
    "SourceStatus",
    "SourcesFile",
    "generate_status_html",
    "main",
    "render_status_page",
]
