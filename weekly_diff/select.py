"""Section quotas and ranked replacement candidates for the summariser."""
from dataclasses import dataclass, replace
import json

from weekly_diff import paths
from weekly_diff.config import Config
from weekly_diff.models import JSONModel
from weekly_diff.score import Scored, signal_score


class InsufficientItems(RuntimeError):
    """Too few qualifying items to publish an issue."""


@dataclass
class Selection(JSONModel):
    chosen: dict[str, list[Scored]]
    backups: dict[str, list[Scored]]

    @classmethod
    def from_dict(cls, data: dict) -> 'Selection':
        return cls(**{kind: {section: [Scored.from_dict(row) for row in rows]
                             for section, rows in data[kind].items()}
                      for kind in ('chosen', 'backups')})


def _rank(item: Scored) -> tuple[float, float, str]:
    return -item.score, -signal_score(item.candidate), item.candidate.key


def _section_rank(item: Scored) -> tuple:
    if item.section == 'github':
        return (-item.candidate.signals.get('stars_gained', 0), *_rank(item))
    return _rank(item)


def select(scored: list[Scored], cfg: Config) -> Selection:
    settings = {s.key: s for s in cfg.issue.sections}
    pools: dict[str, list[Scored]] = {key: [] for key in settings}
    used: set[str] = set()
    for item in sorted(scored, key=_rank):
        if (item.relevant and item.score >= cfg.llm.min_score
                and item.section in pools and item.candidate.key not in used):
            pools[item.section].append(item)
            used.add(item.candidate.key)
    for pool in pools.values():
        pool.sort(key=_section_rank)
    chosen: dict[str, list[Scored]] = {key: [] for key in settings}
    total = 0
    for key, section in settings.items():
        take = min(section.min, len(pools[key]), max(0, cfg.issue.max_items - total))
        chosen[key] = pools[key][:take]
        del pools[key][:take]
        total += take
    while total < cfg.issue.max_items:
        available = [pool[0] for key, pool in pools.items()
                     if pool and len(chosen[key]) < settings[key].max]
        if not available:
            break
        best = min(available, key=_rank)
        chosen[best.section].append(pools[best.section].pop(0))
        total += 1
    for key, section in settings.items():
        while len(chosen[key]) < section.min:
            eligible = [item for origin, pool in pools.items() for item in pool
                        if origin == key or (key == 'quick' and origin != 'github')]
            if not eligible:
                break
            best = min(eligible, key=_section_rank if key != 'quick' else _rank)
            if total >= cfg.issue.max_items:
                donors = [origin for origin in chosen if origin not in {key, 'github'}
                          and len(chosen[origin]) > settings[origin].min]
                if not donors:
                    break
                largest = max(len(chosen[origin]) for origin in donors)
                worst = max((item for origin in donors if len(chosen[origin]) == largest
                             for item in chosen[origin]), key=_rank)
                chosen[worst.section].remove(worst)
                pools[worst.section].append(worst)
                total -= 1
            pools[best.section].remove(best)
            chosen[key].append(replace(best, section=key))
            total += 1
    # Further news overflow can still help meet the overall issue minimum.
    leftovers = sorted((item for pool in pools.values() for item in pool
                        if item.section != 'github'),
                       key=_rank)
    for item in leftovers:
        if (total >= min(cfg.issue.min_items, cfg.issue.max_items)
                or len(chosen['quick']) >= settings['quick'].max):
            break
        pools[item.section].remove(item)
        chosen['quick'].append(replace(item, section='quick'))
        total += 1
    if total < cfg.issue.hard_min_items:
        raise InsufficientItems(f'Only {total} qualifying items; need {cfg.issue.hard_min_items}')
    for items in chosen.values():
        items.sort(key=_section_rank)
    # Backups may serve their original section or quick; build consumes each key once.
    pools['quick'] = [replace(item, section='quick')
                      for origin, pool in pools.items() if origin != 'github' for item in pool]
    for pool in pools.values():
        pool.sort(key=_section_rank)
    selection = Selection(chosen, pools)
    paths.ensure_directory(paths.BUILD)
    (paths.BUILD / 'selection.json').write_text(json.dumps(selection.to_dict(), indent=2, sort_keys=True)
                                               + '\n', encoding='utf-8')
    return selection
