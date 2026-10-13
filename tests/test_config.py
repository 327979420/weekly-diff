from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest
import yaml

from weekly_diff.config import ConfigError, load_config

FIXTURES = Path(__file__).parent / "fixtures"


def test_real_config() -> None:
    cfg = load_config()
    assert cfg.name == "The Weekly Diff"
    assert cfg.base_path == "/weekly-diff"
    assert cfg.issue_url("2026-41") == f"{cfg.site.base_url}/issues/2026-41/"
    assert cfg.sources.github_releases.repos
    assert cfg.llm.timeout_seconds == 180
    assert cfg.llm.max_retries == 2
    with pytest.raises(FrozenInstanceError):
        cfg.site.language = "fr"
    assert isinstance(cfg.issue.sections, tuple)


@pytest.mark.parametrize("case", json.loads((FIXTURES / "invalid-configs.json").read_text()))
def test_invalid_config(case: dict, tmp_path: Path) -> None:
    raw = yaml.safe_load((FIXTURES / "config.yaml").read_text())
    target = raw
    for key in case["path"][:-1]:
        target = target[key]
    key = case["path"][-1]
    if case.get("delete"):
        del target[key]
    else:
        target[key] = case["value"]
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(raw))
    with pytest.raises(ConfigError) as error:
        load_config(path)
    assert case["error"] in str(error.value)


def test_fixture_and_missing_file(tmp_path: Path) -> None:
    assert load_config(FIXTURES / "config.yaml").base_path == "/roundup"
    with pytest.raises(ConfigError, match="config"):
        load_config(tmp_path / "absent")


def test_llm_defaults(tmp_path: Path) -> None:
    raw = yaml.safe_load((FIXTURES / "config.yaml").read_text())
    del raw['llm']['timeout_seconds']
    del raw['llm']['max_retries']
    path = tmp_path / 'config.yaml'
    path.write_text(yaml.safe_dump(raw))
    cfg = load_config(path)
    assert cfg.llm.timeout_seconds == 180
    assert cfg.llm.max_retries == 2


@pytest.mark.parametrize('path', [('tagline_zh',), ('tags_zh', 'try'),
                                  ('issue', 'sections', 0, 'title_zh')])
@pytest.mark.parametrize('value', ['', '  ', None, 42])
def test_chinese_labels_validated(path: tuple, value: object, tmp_path: Path) -> None:
    raw = yaml.safe_load((FIXTURES / 'config.yaml').read_text())
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    config = tmp_path / 'config.yaml'
    config.write_text(yaml.safe_dump(raw))
    with pytest.raises(ConfigError):
        load_config(config)
