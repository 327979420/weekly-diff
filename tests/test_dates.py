from datetime import datetime, timedelta, timezone

import pytest
from weekly_diff.dates import issue_id_for, issue_period, parse_issue_id, window


@pytest.mark.parametrize(("value", "expected"), [
    ("2026-12-31T00:00:00+00:00", "2026-53"),
    ("2027-01-01T00:00:00+00:00", "2026-53"),
    ("2027-01-04T00:00:00+00:00", "2027-01"),
    ("2026-10-11T21:00:00+00:00", "2026-41"),
    ("2027-01-04T08:00:00+11:00", "2026-53"),
])
def test_issue_id(value: str, expected: str) -> None:
    assert issue_id_for(datetime.fromisoformat(value)) == expected


@pytest.mark.parametrize("value", ["2026-54", "2027-53", "2026-00", "2026-1", "x", "0000-01"])
def test_invalid_issue(value: str) -> None:
    with pytest.raises(ValueError):
        parse_issue_id(value)


def test_period_and_window() -> None:
    assert parse_issue_id("2026-53") == (2026, 53)
    monday, sunday = issue_period("2026-53")
    assert monday == datetime(2026, 12, 28, tzinfo=timezone.utc)
    assert sunday == datetime(2027, 1, 3, tzinfo=timezone.utc)
    start, end = window(sunday, 7)
    assert end == sunday
    assert end - start == timedelta(days=7)


def test_naive_dates_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        issue_id_for(datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="timezone-aware"):
        window(datetime(2026, 1, 1), 7)
    with pytest.raises(ValueError):
        window(datetime.now(timezone.utc), -1)
