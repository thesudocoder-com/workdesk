from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


TORONTO_TIMEZONE = ZoneInfo("America/Toronto")


def business_timezone() -> ZoneInfo:
    try:
        from Application.Settings.Service import get_workspace
        workspace = get_workspace()
        return ZoneInfo(workspace.timezone) if workspace else TORONTO_TIMEZONE
    except Exception:
        return TORONTO_TIMEZONE


def now_utc() -> datetime:
    return datetime.now(UTC)


def to_toronto(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(business_timezone())


def today_toronto() -> date:
    return datetime.now(business_timezone()).date()
