from dataclasses import replace
import json
from pathlib import Path

import pytest

from weekly_diff import paths
from weekly_diff.config import Config, load_config
from weekly_diff.models import Candidate
from weekly_diff.score import Scored
from weekly_diff.select import InsufficientItems, Selection, select

DATA = json.loads((Path(__file__).parent / 'fixtures/shortlist.json').read_text())


def items(section: str, count: int, source_type: str = 'rss') -> list[Scored]:
    base = Candidate.from_dict(DATA['candidate'])
    return [Scored(replace(base, key=f'{section}:{i}', source_type=source_type,
                           signals={'stars_gained': i, 'stars_total': 10000 - i}),
                   True, section, 'builders', 10 - (i % 5), 'Useful') for i in range(count)]


def small_config() -> Config:
    cfg = load_config()
    return replace(cfg, issue=replace(cfg.issue, min_items=6, max_items=8, hard_min_items=3,
                   sections=tuple(replace(s, min=1, max=2) for s in cfg.issue.sections)))


def test_quotas_cap_backups_and_github_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, 'BUILD', tmp_path)
    cfg = load_config()
    scored = [item for section in cfg.issue.sections for item in items(section.key, 8)]
    result = select(scored, cfg)
    assert sum(map(len, result.chosen.values())) == cfg.issue.max_items
    for section in cfg.issue.sections:
        assert section.min <= len(result.chosen[section.key]) <= section.max
    stars = [s.candidate.signals['stars_gained'] for s in result.chosen['github']]
    assert stars == sorted(stars, reverse=True)
    assert stars[0] == 7
    chosen = {s.candidate.key for pool in result.chosen.values() for s in pool}
    backups = {s.candidate.key for pool in result.backups.values() for s in pool}
    assert chosen.isdisjoint(backups)
    assert len(chosen | backups) == len(scored)
    assert Selection.from_dict(json.loads((tmp_path / 'selection.json').read_text())) == result


def test_quick_topup_and_no_duplicate_or_ineligible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, 'BUILD', tmp_path)
    cfg = small_config()
    scored = items('models', 5) + items('tools', 2)
    scored += [scored[0], replace(scored[0], candidate=replace(scored[0].candidate, key='bad'), relevant=False),
               replace(scored[0], candidate=replace(scored[0].candidate, key='low'), score=4)]
    result = select(scored, cfg)
    assert {key: len(value) for key, value in result.chosen.items()} == {'models': 2, 'tools': 2, 'github': 0, 'quick': 2}
    chosen = [s for pool in result.chosen.values() for s in pool]
    assert len({s.candidate.key for s in chosen}) == len(chosen)
    assert all(s.section == 'quick' for s in result.chosen['quick'])
    assert all(s.candidate.key not in {'bad', 'low'} for s in chosen)
    assert len(result.backups['models']) == 1


def test_hard_sections_and_insufficient_no_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, 'BUILD', tmp_path)
    cfg = small_config()
    with pytest.raises(InsufficientItems):
        select(items('github', 8, 'github_trending'), cfg)
    assert not (tmp_path / 'selection.json').exists()
    cfg = replace(cfg, issue=replace(cfg.issue, hard_min_items=2))
    result = select(items('github', 8, 'github_trending'), cfg)
    assert len(result.chosen['github']) == 2
    assert result.chosen['quick'] == []


def test_total_cap_even_when_minima_exceed_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, 'BUILD', tmp_path)
    cfg = small_config()
    cfg = replace(cfg, issue=replace(cfg.issue, max_items=3, min_items=3))
    result = select([item for section in cfg.issue.sections for item in items(section.key, 3)], cfg)
    assert sum(map(len, result.chosen.values())) == 3


@pytest.mark.parametrize('cap', [12, 13, 15])
def test_empty_quick_section_gets_minimum(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cap: int) -> None:
    monkeypatch.setattr(paths, 'BUILD', tmp_path)
    cfg = load_config()
    cfg = replace(cfg, issue=replace(cfg.issue, max_items=cap))
    scored = (items('models', 8, 'huggingface') + items('tools', 8, 'github_release')
              + items('github', 6, 'github_trending'))
    scored += [replace(items('models', 1)[0], candidate=replace(scored[0].candidate, key='irrelevant'), relevant=False),
               replace(items('models', 1)[0], candidate=replace(scored[0].candidate, key='low'), score=4)]
    result = select(scored, cfg)
    assert len(result.chosen['quick']) == 2
    assert len(result.chosen['github']) == 4
    assert sum(map(len, result.chosen.values())) == min(cap, 14)
    for section in cfg.issue.sections:
        assert section.min <= len(result.chosen[section.key]) <= section.max
    chosen = [item for pool in result.chosen.values() for item in pool]
    assert len({item.candidate.key for item in chosen}) == len(chosen)
    assert all(item.section == 'quick' for item in result.chosen['quick'] + result.backups['quick'])
    assert all(item.candidate.source_type != 'github_trending' for item in result.backups['quick'])
    assert all(item.candidate.key not in {'irrelevant', 'low'} for item in result.backups['quick'] + chosen)
    assert [item.score for item in result.backups['quick']] == sorted(
        (item.score for item in result.backups['quick']), reverse=True)
    if cap == 12:
        # Both equally large news sections donate their lowest-scored selected item.
        assert len(result.chosen['models']) == len(result.chosen['tools']) == 3
        assert min(item.score for item in result.chosen['models']) == 9
        assert min(item.score for item in result.chosen['tools']) == 9


@pytest.mark.parametrize('section', ['models', 'tools', 'github', 'quick'])
def test_try_now_preferred_with_quotas_and_threshold(section: str, tmp_path: Path,
                                                    monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, 'BUILD', tmp_path)
    cfg = small_config()
    cfg = replace(cfg, issue=replace(cfg.issue, hard_min_items=1, max_items=1, min_items=1,
                  sections=tuple(replace(s, min=1 if s.key == section else 0, max=1)
                                 for s in cfg.issue.sections)))
    pool = items(section, 3)
    pool[0] = replace(pool[0], score=10, try_now=False)
    pool[1] = replace(pool[1], score=5, try_now=True)
    pool[2] = replace(pool[2], score=4, try_now=True)
    result = select(pool, cfg)
    assert result.chosen[section] == [pool[1]]
    assert all(s.candidate.key != pool[2].candidate.key for rows in result.backups.values() for s in rows)
