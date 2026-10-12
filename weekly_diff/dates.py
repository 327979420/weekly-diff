"""UTC issue identifiers and reporting windows."""
import re
from datetime import datetime, timedelta, timezone


def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return dt.astimezone(timezone.utc)


def issue_id_for(dt: datetime) -> str:
    year, week, _ = as_utc(dt).isocalendar()
    return f"{year:04d}-{week:02d}"


def parse_issue_id(issue_id: str) -> tuple[int, int]:
    """Return the ISO year and week, rejecting nonexistent weeks."""
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}", issue_id):
        raise ValueError("issue id must be YYYY-WW")
    year, week = map(int, issue_id.split("-"))
    datetime.fromisocalendar(year, week, 1)
    return year, week


def window(now: datetime, lookback_days: int) -> tuple[datetime, datetime]:
    if type(lookback_days) is not int or lookback_days < 0:
        raise ValueError("lookback_days must be a nonnegative integer")
    end = as_utc(now)
    return end - timedelta(days=lookback_days), end


def issue_period(issue_id: str) -> tuple[datetime, datetime]:
    """Return Monday and Sunday at midnight UTC for an ISO week."""
    year, week = parse_issue_id(issue_id)
    monday = datetime.fromisocalendar(year, week, 1).replace(tzinfo=timezone.utc)
    return monday, monday + timedelta(days=6)
