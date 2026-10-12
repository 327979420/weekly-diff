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


def test_committed_legacy_issue_loads_and_renders(tmp_path: Path) -> None:
    from weekly_diff.config import load_config
    from weekly_diff.site import render_site

    source = Path(__file__).parents[1] / 'data/issues/2026-42.json'
    raw = source.read_text()
    issue = Issue.from_dict(json.loads(raw))
    assert issue.sixty_seconds_zh == []
    assert all(item.zh is None and item.emoji is None and item.image_url is None for item in issue.items())
    issues = tmp_path / 'issues'
    issues.mkdir()
    (issues / source.name).write_text(raw)
    render_site(load_config(), issues, tmp_path / 'site')
    page = (tmp_path / 'site/issues/2026-42/index.html').read_text()
    assert '2026-42' in page and next(issue.items()).source_url in page
