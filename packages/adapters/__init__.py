"""``bayre-adapters`` — data-source adapters.

Public surface (importable as ``adapters.<module>`` after install):

    from adapters._base import (
        DataSourceAdapter,
        Capability,
        License,
        RawSnapshot,
        MetricValue,
    )
    from adapters.redfin_csv import RedfinCsvAdapter

Per ``docs/design.md`` §3 and §10: adapters are the *only* code in this layer
that does I/O. Everything downstream (resolver, ETL, finance) consumes
``RawSnapshot`` and never touches HTTP / files.

Bronze immutability (per ``docs/implementation-plan.md`` Phase 0): each adapter
caches the raw payload before parsing — never mutates it.
"""

from ._base import (
    Capability,
    DataSourceAdapter,
    License,
    MetricValue,
    RawSnapshot,
)

__all__ = [
    "Capability",
    "DataSourceAdapter",
    "License",
    "MetricValue",
    "RawSnapshot",
]
