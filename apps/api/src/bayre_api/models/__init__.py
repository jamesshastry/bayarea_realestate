"""SQLAlchemy 2.0 declarative models — mapped 1:1 to `docs/datamodel.md`.

Importing this module registers every table with `Base.metadata`, which is
what Alembic autogenerate reads. New models MUST be imported here.
"""

from bayre_api.models.attendance_zone import AttendanceZone
from bayre_api.models.base import Base
from bayre_api.models.data_source import DataSource
from bayre_api.models.geographic_area import GeographicArea
from bayre_api.models.listing import Listing
from bayre_api.models.market_signal import MarketSignal
from bayre_api.models.market_snapshot import MarketSnapshot
from bayre_api.models.parcel import Parcel
from bayre_api.models.sale import Sale
from bayre_api.models.school import School
from bayre_api.models.school_district import SchoolDistrict
from bayre_api.models.source_fetch import SourceFetch

__all__ = [
    "AttendanceZone",
    "Base",
    "DataSource",
    "GeographicArea",
    "Listing",
    "MarketSignal",
    "MarketSnapshot",
    "Parcel",
    "Sale",
    "School",
    "SchoolDistrict",
    "SourceFetch",
]
