"""``bayre-domain`` — Pydantic v2 models shared across packages.

Public surface (importable as ``domain.<module>`` after install):

    from domain.snapshot import (
        SCHEMA_VERSION,
        CitySnapshot,
        DataQuality,
        FreshnessTier,
        MetricsBlock,
        SnapshotFile,
    )
    from domain.period import Month, Period, Week
    from domain.geographic_area import GeoKind, GeographicArea

These models are the inter-track contract surface (see ``docs/contracts.md`` C2).
Bumping any field requires bumping ``SCHEMA_VERSION`` in snapshot.py.
"""

from .geographic_area import GeographicArea, GeoKind
from .period import Month, Period, Week
from .snapshot import (
    SCHEMA_VERSION,
    CitySnapshot,
    DataQuality,
    FreshnessTier,
    MetricsBlock,
    SnapshotFile,
)

__all__ = [
    "SCHEMA_VERSION",
    "CitySnapshot",
    "DataQuality",
    "FreshnessTier",
    "GeoKind",
    "GeographicArea",
    "MetricsBlock",
    "Month",
    "Period",
    "SnapshotFile",
    "Week",
]
