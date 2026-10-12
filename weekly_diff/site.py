"""Render the offline issue archive as a small static website and RSS feed."""
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


def _view(issue: Issue, cfg: Config, env: Environment) -> dict[str, Any]:
    parse_issue_id(issue.id)
    for item in issue.items():
        _domain(item.source_url)
    view = {
        'issue': issue,
        'title': f'{cfg.name} — Issue {issue.id}',
        'period': _period(issue, cfg.site.timezone),
        'url': cfg.issue_url(issue.id),
        'path': f'{cfg.base_path}/issues/{issue.id}/',
        'description': issue.sixty_seconds[0] if issue.sixty_seconds else cfg.tagline,
        'pub_date': format_datetime(issue.published_at),
    }
    # Render HTML first, then let feed.xml escape that string as XML text.
    view['feed_description'] = str(env.get_template('feed.xml').make_module({'cfg': cfg, 'views': []}).feed_description(issue, cfg))
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
    views = [_view(issue, cfg, env) for issue in sorted(issues, key=lambda issue: issue.id, reverse=True)]
    if len({view['issue'].id for view in views}) != len(views):
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

    latest = views[0] if views else None
    write('index.html', 'home.html', view=latest, title=cfg.name,
          description=latest['description'] if latest else cfg.tagline,
          canonical=f'{cfg.site.base_url}/', page_path=f'{cfg.base_path}/')
    for view in views:
        write(f"issues/{view['issue'].id}/index.html", 'issue.html', view=view,
              title=view['title'], description=view['description'], canonical=view['url'], page_path=view['path'])
    write('archive/index.html', 'archive.html', views=views, title=f'Archive · {cfg.name}',
          description=cfg.tagline, canonical=f'{cfg.site.base_url}/archive/', page_path=f'{cfg.base_path}/archive/')
    write('404.html', '404.html', title=f'Page not found · {cfg.name}', description=cfg.tagline,
          canonical=f'{cfg.site.base_url}/404.html', page_path=f'{cfg.base_path}/404.html')
    write('feed.xml', 'feed.xml', views=views[:max(0, cfg.site.feed_items)])
    (out_dir / '.nojekyll').touch()
    (out_dir / 'assets').mkdir()
    shutil.copyfile(paths.ROOT / 'static/style.css', out_dir / 'assets/style.css')
    written.extend([out_dir / '.nojekyll', out_dir / 'assets/style.css'])
    return written
