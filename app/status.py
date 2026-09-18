from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum


class Level(str, Enum):
    OK = "ok"
    WARNING = "warning"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass
class StatusEntry:
    label: str
    level: Level
    detail: str = ""
    url: str | None = None
    checked_at: datetime = field(default_factory=lambda: now_cet())


def now_cet() -> datetime:
    # RCE-diensten loggen in CET/CEST; UTC+2 volstaat als eenvoudige benadering
    # zoals ook in service-dashboard wordt gedaan.
    return (datetime.now(timezone.utc) + timedelta(hours=2)).replace(tzinfo=None)
