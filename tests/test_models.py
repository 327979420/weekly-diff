from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import pytest

from weekly_diff.models import Candidate, Issue, Item

DATA = json.loads((Path(__file__).parent / "fixtures/models.json").read_text())


def test_all_roundtrips_and_order() -> None:
    candidate = Candidate.from_dict(DATA["candidate"])
    item = Item.from_dict(DATA["item"])
    issue = Issue.from_dict(DATA["issue"])
    second = Item.from_dict({**DATA["item"], "key": "b", "section": "tools"})
    issue.sections = {"tools": [second], "models": [item]}
    for model in (candidate, item, issue):
        assert type(model).from_dict(json.loads(json.dumps(model.to_dict()))) == model
    assert list(issue.items()) == [second, item]
    assert list(Issue.from_dict(issue.to_dict()).sections) == ["tools", "models"]


def test_dates_are_utc_and_optional() -> None:
    item = Item.from_dict(DATA["item"])
    item.published_at = datetime(2026, 10, 12, 8, tzinfo=timezone(timedelta(hours=11)))
    assert item.to_dict()["published_at"] == "2026-10-11T21:00:00+00:00"
    for kind, key in ((Item, "item"), (Candidate, "candidate")):
        model = kind.from_dict({**DATA[key], "published_at": None})
        assert kind.from_dict(model.to_dict()) == model
    item.published_at = datetime(2026, 1, 1)
    with pytest.raises(ValueError, match="timezone-aware"):
        item.to_dict()
