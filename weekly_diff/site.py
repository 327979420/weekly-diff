"""Render the offline issue archive as a small static website and RSS feed."""
from dataclasses import replace
from email.utils import format_datetime
import json
from pathlib import Path
import shutil
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from weekly_diff import paths
from weekly_diff.config import Config
from weekly_diff.dates import parse_issue_id
from weekly_diff.models import Issue


STRINGS = {
    'en': dict(latest='Latest', archive='Archive', sixty='This week in 60 seconds',
               more='More', why='Why it matters:', builders='For builders:', source='Source ↗',
               stars='+{n} ★ this week', issue='Issue {id}', soon='first issue coming soon.',
               missing='', skip='Skip to content', navigation='Main navigation',
               browse='Browse all issues', subscribe='Subscribe via RSS',
               not_found='Page not found', lost='This page could not be found.'),
    'zh': dict(latest='最新一期', archive='往期归档', sixty='60 秒速览',
               more='展开', why='为什么重要：', builders='开发者提示：', source='原文 ↗',
               stars='本周 +{n} ★', issue='第 {week} 期 · {year}', soon='首期即将发布。',
               missing='本期暂无中文版', skip='跳至正文', navigation='主导航',
               browse='浏览全部期刊', subscribe='通过 RSS 订阅',
               not_found='页面未找到', lost='找不到此页面。'),
}
SECTION_ICONS = {'models': '🧠', 'tools': '🛠️', 'github': '⭐', 'quick': '⚡'}
TEXT_FIELDS = ('headline', 'summary', 'why_it_matters', 'for_builders')


def _localized(issue: Issue, language: str) -> tuple[Issue, bool]:
    if language == 'en':
        return issue, False
    missing = len(issue.sixty_seconds_zh) < len(issue.sixty_seconds)
    sections = {}
    for key, items in issue.sections.items():
        translated = []
        for item in items:
            zh = item.zh or {}
            missing |= any(getattr(item, field) and not zh.get(field) for field in TEXT_FIELDS)
            translated.append(replace(item, **{
                field: zh.get(field) or getattr(item, field) for field in TEXT_FIELDS}))
        sections[key] = translated
    bullets = [issue.sixty_seconds_zh[i] if i < len(issue.sixty_seconds_zh)
               and issue.sixty_seconds_zh[i] else bullet
               for i, bullet in enumerate(issue.sixty_seconds)]
    missing |= any(not bullet for bullet in issue.sixty_seconds_zh)
    return replace(issue, sections=sections, sixty_seconds=bullets), bool(missing)


def _period(issue: Issue, timezone: str) -> str:
    start, end = (value.astimezone(ZoneInfo(timezone)) for value in (issue.period_start, issue.period_end))
    if start.date() == end.date():
        return f'{start.day} {start:%b %Y}'
    if (start.year, start.month) == (end.year, end.month):
        return f'{start.day}–{end.day} {end:%b %Y}'
    if start.year == end.year:
        return f'{start.day} {start:%b}–{end.day} {end:%b %Y}'
    return f'{start.day} {start:%b %Y}–{end.day} {end:%b %Y}'


def _domain(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {'http', 'https'} or not parts.hostname:
        raise ValueError('Issue source URL must use HTTP or HTTPS')
    return parts.hostname


def _view(issue: Issue, cfg: Config, env: Environment, language: str) -> dict[str, Any]:
    parse_issue_id(issue.id)
    for item in issue.items():
        _domain(item.source_url)
        if item.image_url:
            _domain(item.image_url)
    issue, missing = _localized(issue, language)
    strings = STRINGS[language]
    prefix = '/zh' if language == 'zh' else ''
    label = strings['issue'].format(id=issue.id, year=issue.id[:4], week=issue.id[5:])
    view = {
        'missing': missing, 'label': label,
        'issue': issue,
        'title': f'{cfg.name} — {label}',
        'period': _period(issue, cfg.site.timezone),
        'url': f'{cfg.site.base_url}{prefix}/issues/{issue.id}/',
        'path': f'{cfg.base_path}{prefix}/issues/{issue.id}/',
        'description': issue.sixty_seconds[0] if issue.sixty_seconds else (cfg.tagline_zh if language == 'zh' else cfg.tagline),
        'pub_date': format_datetime(issue.published_at),
    }
    # Render HTML first, then let feed.xml escape that string as XML text.
    view['feed_description'] = str(env.get_template('feed_description.html').make_module({}).feed_description(issue, cfg, strings, missing))
    return view


def render_site(cfg: Config, issues_dir: Path, out_dir: Path) -> list[Path]:
    """Rebuild all output from saved issues, without network or LLM calls."""
    issues_dir, out_dir = Path(issues_dir), Path(out_dir)
    if issues_dir.resolve().is_relative_to(out_dir.resolve()):
        raise ValueError('Site output must not contain the issue archive')
    env = Environment(loader=FileSystemLoader(paths.ROOT / 'templates'),
                      autoescape=True, undefined=StrictUndefined,
                      trim_blocks=True, lstrip_blocks=True)
    env.filters['domain'] = _domain
    issues = [Issue.from_dict(json.loads(path.read_text(encoding='utf-8')))
              for path in issues_dir.glob('*.json')]
    issues.sort(key=lambda issue: issue.id, reverse=True)
    views_by_language = {language: [_view(issue, cfg, env, language) for issue in issues]
                         for language in STRINGS}
    if len({issue.id for issue in issues}) != len(issues):
        raise ValueError('Duplicate issue IDs')
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    written: list[Path] = []

    def write(relative: str, template: str, **context: Any) -> None:
        target = out_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template(template).render(cfg=cfg, **context), encoding='utf-8')
        written.append(target)

    for language, views in views_by_language.items():
        prefix = 'zh/' if language == 'zh' else ''
        root = f'{cfg.base_path}/{prefix}'
        base_url = f'{cfg.site.base_url}/{prefix}'
        strings = STRINGS[language]
        tagline = cfg.tagline_zh if language == 'zh' else cfg.tagline
        common = dict(language=language, html_lang='zh-CN' if language == 'zh' else 'en',
                      strings=strings, root=root, base_url=base_url, tagline=tagline,
                      tags=cfg.tags_zh if language == 'zh' else cfg.tags,
                      icons=SECTION_ICONS)

        def page(relative: str, template: str, **context: Any) -> None:
            route = relative.removesuffix('index.html')
            write(prefix + relative, template, **common, **context,
                  canonical=base_url + route, page_path=root + route,
                  en_url=f'{cfg.site.base_url}/{route}',
                  zh_url=f'{cfg.site.base_url}/zh/{route}')

        latest = views[0] if views else None
        page('index.html', 'home.html', view=latest, title=cfg.name,
             description=latest['description'] if latest else tagline)
        for view in views:
            page(f"issues/{view['issue'].id}/index.html", 'issue.html', view=view,
                 title=view['title'], description=view['description'])
        page('archive/index.html', 'archive.html', views=views,
             title=f"{strings['archive']} · {cfg.name}", description=tagline)
        page('404.html', '404.html', title=f"{strings['not_found']} · {cfg.name}", description=tagline)
        write(prefix + 'feed.xml', 'feed.xml', **common, views=views[:max(0, cfg.site.feed_items)])
    (out_dir / '.nojekyll').touch()
    (out_dir / 'assets').mkdir()
    shutil.copyfile(paths.ROOT / 'static/style.css', out_dir / 'assets/style.css')
    written.extend([out_dir / '.nojekyll', out_dir / 'assets/style.css'])
    return written
