from argparse import Namespace
from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import shutil
from xml.etree import ElementTree

from bs4 import BeautifulSoup
import feedparser
import pytest

from weekly_diff import build, paths, pipeline
from weekly_diff.config import load_config
from weekly_diff.models import Issue
from weekly_diff.site import _period, render_site

FIXTURES = Path(__file__).parent / 'fixtures/issues'


@pytest.fixture
def issue_fixtures(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Keep the separate legacy sample out of the two-issue archive."""
    directory = tmp_path_factory.mktemp('archive-fixtures')
    for name in ('2026-41.json', '2026-42.json'):
        shutil.copyfile(FIXTURES / name, directory / name)
    return directory


def test_complete_site(issue_fixtures: Path, tmp_path: Path) -> None:
    cfg = load_config()
    out = tmp_path / 'site'
    out.mkdir()
    (out / 'stale.html').touch()
    written = render_site(cfg, issue_fixtures, out)
    expected = {'index.html', 'issues/2026-41/index.html', 'issues/2026-42/index.html',
                'archive/index.html', 'feed.xml', '404.html', '.nojekyll', 'assets/style.css'}
    expected |= {'zh/' + path for path in expected if path.endswith(('.html', '.xml'))}
    assert {str(path.relative_to(out)) for path in written} == expected
    assert not (out / 'stale.html').exists()
    home = BeautifulSoup((out / 'index.html').read_text(), 'html.parser')
    assert home.h1.get_text(' ', strip=True) == 'Issue 2026-42 · 12–18 Oct 2026'
    assert len(home.select('article')) == 15
    assert [section['id'] for section in home.select('section[id]')] == [section.key for section in cfg.issue.sections]
    assert '+0 ★ this week' in home.get_text()
    assert len(home.select('article strong')) == 19
    assert cfg.tags['try'] in home.get_text()
    assert 'Archived name' not in home.get_text()
    assert len(home.select('h1')) == 1
    assert home.select_one('main#main')
    archive = BeautifulSoup((out / 'archive/index.html').read_text(), 'html.parser')
    assert [a['href'] for a in archive.select('.history-row > a')] == [f'{cfg.base_path}/issues/{week}/' for week in ('2026-42', '2026-41')]
    assert 'Week 42: tools for builders.' in archive.get_text()
    for path in out.rglob('*.html'):
        soup = BeautifulSoup(path.read_text(), 'html.parser')
        assert soup.html['lang'] == ('zh-CN' if path.is_relative_to(out / 'zh') else 'en')
        assert not soup.select('script, img, iframe')
        assert soup.select_one('link[rel=canonical]')['href'].startswith(cfg.site.base_url)
        assert soup.select_one('meta[property="og:url"]')['content'] == soup.select_one('link[rel=canonical]')['href']
        assert soup.select_one('meta[name=description]')['content']
        for link in soup.select('[href]'):
            url = link['href']
            if not url.startswith(('https://', 'http://')):
                assert url.startswith((cfg.base_path + '/', 'data:image/svg+xml,'))
        for link in soup.select('article a[rel]'):
            assert 'noopener' in link['rel']
    assert (out / 'index.html').stat().st_size + (out / 'assets/style.css').stat().st_size < 50_000


def test_feed_and_escaping(issue_fixtures: Path, tmp_path: Path) -> None:
    cfg = load_config()
    render_site(cfg, issue_fixtures, tmp_path)
    html = (tmp_path / 'index.html').read_text()
    xml = (tmp_path / 'feed.xml').read_text()
    assert '<script>' not in html and '&lt;script&gt;alert(1)&lt;/script&gt;' in html
    assert '&amp;lt;script&amp;gt;' in xml
    tree = ElementTree.fromstring(xml)
    entries = tree.findall('channel/item')
    assert len(entries) == 2
    assert entries[0].find('guid').attrib == {'isPermaLink': 'true'}
    description = entries[0].findtext('description')
    assert '<script>' not in description
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in description
    for link in BeautifulSoup(description, 'html.parser').select('a'):
        assert link['href'].startswith('https://')
    feed = feedparser.parse(xml)
    assert not feed.bozo
    assert [entry.link for entry in feed.entries] == [cfg.issue_url(week) for week in ('2026-42', '2026-41')]
    assert [entry.published_parsed[:6] for entry in feed.entries] == [(2026, 10, 18, 21, 0, 0), (2026, 10, 11, 21, 0, 0)]
    render_site(replace(cfg, site=replace(cfg.site, feed_items=1)), issue_fixtures, tmp_path)
    assert len(feedparser.parse((tmp_path / 'feed.xml').read_text()).entries) == 1


def test_empty_and_config_changes(tmp_path: Path) -> None:
    cfg = load_config()
    cfg = replace(cfg, name='Renamed & <roundup>', tagline='New tagline',
                  site=replace(cfg.site, base_url='https://example.org/news', language='fr'))
    out = tmp_path / 'site'
    render_site(cfg, tmp_path / 'missing', out)
    soup = BeautifulSoup((out / 'index.html').read_text(), 'html.parser')
    assert soup.h1.text == f'{cfg.name} — first issue coming soon.'
    assert soup.html['lang'] == 'en'
    assert soup.select_one('link[rel=stylesheet]')['href'] == '/news/assets/style.css'
    assert not feedparser.parse((out / 'feed.xml').read_text()).entries


def test_missing_sections_and_optional_fields(tmp_path: Path) -> None:
    data = json.loads((FIXTURES / '2026-42.json').read_text())
    data['sections'] = {'models': data['sections']['models'][1:2]}
    source = tmp_path / 'issues'
    source.mkdir()
    (source / '2026-42.json').write_text(json.dumps(data))
    render_site(load_config(), source, tmp_path / 'site')
    soup = BeautifulSoup((tmp_path / 'site/index.html').read_text(), 'html.parser')
    assert [s['id'] for s in soup.select('section[id]')] == ['models']
    assert 'How to try it:' not in soup.get_text()
    assert 'stars this week' not in soup.get_text()


@pytest.mark.parametrize(('start', 'end', 'expected'), [
    ('2026-10-11T13:00:00+00:00', '2026-10-11T14:00:00+00:00', '12 Oct 2026'),
    ('2026-09-28T00:00:00+00:00', '2026-10-04T00:00:00+00:00', '28 Sep–4 Oct 2026'),
    ('2026-12-28T00:00:00+00:00', '2027-01-03T00:00:00+00:00', '28 Dec 2026–3 Jan 2027'),
])
def test_period(start: str, end: str, expected: str) -> None:
    issue = Issue.from_dict(json.loads((FIXTURES / '2026-42.json').read_text()))
    issue.period_start, issue.period_end = datetime.fromisoformat(start), datetime.fromisoformat(end)
    assert _period(issue, 'Australia/Melbourne') == expected


def test_pipeline_render(issue_fixtures: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, 'ISSUES', issue_fixtures)
    monkeypatch.setattr(paths, 'SITE', tmp_path / 'site')
    pipeline.render(load_config(), Namespace(dry_run=True))
    assert (paths.SITE / 'issues/2026-42/index.html').exists()


def test_dry_run_combines_archive_and_replaces_same_week(issue_fixtures: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / 'data/issues'
    shutil.copytree(issue_fixtures, source)
    monkeypatch.setattr(paths, 'ISSUES', source)
    monkeypatch.setattr(paths, 'SITE', tmp_path / 'site')
    before = {p.name: p.read_bytes() for p in source.iterdir()}
    issue = Issue.from_dict(json.loads(before['2026-42.json']))
    issue.sixty_seconds[0] = 'Preview replacement'
    build._render(load_config(), issue, True)
    assert 'Preview replacement' in (paths.SITE / 'index.html').read_text()
    assert (paths.SITE / 'issues/2026-41/index.html').exists()
    assert len(feedparser.parse((paths.SITE / 'feed.xml').read_text()).entries) == 2
    issue.id = '2026-43'
    build._render(load_config(), issue, True)
    assert 'Issue 2026-43' in (paths.SITE / 'index.html').read_text()
    assert (paths.SITE / 'issues/2026-42/index.html').exists()
    assert before == {p.name: p.read_bytes() for p in source.iterdir()}


@pytest.mark.parametrize(('field', 'value'), [('id', '../escape'), ('source_url', 'javascript:alert(1)'), ('image_url', 'javascript:alert(1)')])
def test_invalid_paths_and_links_preserve_output(tmp_path: Path, field: str, value: str) -> None:
    data = json.loads((FIXTURES / '2026-42.json').read_text())
    if field == 'id':
        data[field] = value
    else:
        data['sections']['models'][0][field] = value
    source = tmp_path / 'issues'
    source.mkdir()
    (source / 'invalid.json').write_text(json.dumps(data))
    out = tmp_path / 'site'
    out.mkdir()
    (out / 'sentinel').touch()
    with pytest.raises(ValueError):
        render_site(load_config(), source, out)
    assert (out / 'sentinel').exists()


def test_output_cannot_delete_input(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match='must not contain'):
        render_site(load_config(), tmp_path / 'issues', tmp_path)


BILINGUAL = FIXTURES.parent / 'bilingual_issues'


def test_bilingual_pages_and_counterparts(tmp_path: Path) -> None:
    cfg = load_config()
    render_site(cfg, BILINGUAL, tmp_path)
    for path in tmp_path.rglob('*.html'):
        relative = path.relative_to(tmp_path).as_posix()
        chinese = relative.startswith('zh/')
        route = relative.removeprefix('zh/').removesuffix('index.html')
        soup = BeautifulSoup(path.read_text(), 'html.parser')
        assert soup.html['lang'] == ('zh-CN' if chinese else 'en')
        expected = {'en': f'{cfg.site.base_url}/{route}',
                    'zh-CN': f'{cfg.site.base_url}/zh/{route}'}
        assert {link['hreflang']: link['href'] for link in soup.select('link[hreflang]')} == expected
        assert {link['hreflang']: link['href'] for link in soup.select('.languages a')} == expected
        assert soup.select_one('link[type="application/rss+xml"]')['href'] == f'{cfg.base_path}/' + ('zh/' if chinese else '') + 'feed.xml'
        assert not soup.select('script, iframe')
    home = BeautifulSoup((tmp_path / 'zh/index.html').read_text(), 'html.parser')
    assert '60 秒速览' in home.get_text()
    assert cfg.tagline_zh in home.get_text()
    assert cfg.tags_zh['try'] in home.get_text()
    assert all(section.title_zh in home.get_text() for section in cfg.issue.sections)
    assert '根据原文整理的简短摘要。' in home.get_text()
    assert '本期暂无中文版' not in home.get_text()
    assert '本周 +0 ★' in home.get_text()
    assert len(home.select('details > summary')) == 15
    assert all(summary.text == '展开' for summary in home.select('details > summary'))
    for prefix in ('', 'zh/'):
        html = (tmp_path / prefix / 'index.html').read_text()
        soup = BeautifulSoup(html, 'html.parser')
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
        assert len(soup.select('img')) == 0
        assert len(soup.select('.image-band')) == 15
        for card in soup.select('.card'):
            img = card.find('img')
            if img:
                assert img['alt'] == card.h3.text
                assert img['loading'] == 'lazy'
                assert img['referrerpolicy'] == 'no-referrer'
                assert (img['width'], img['height']) == ('640', '360')
        assert len(html.encode()) + (tmp_path / 'assets/style.css').stat().st_size < 60_000
    old = BeautifulSoup((tmp_path / 'zh/issues/2026-41/index.html').read_text(), 'html.parser')
    assert '本期暂无中文版' in old.get_text()
    assert 'A concise summary based on the source text.' in old.get_text()
    archive = BeautifulSoup((tmp_path / 'zh/archive/index.html').read_text(), 'html.parser')
    assert '第 42 周：开发者工具。' in archive.get_text()
    assert '本期暂无中文版' in archive.get_text()
    feed = feedparser.parse((tmp_path / 'zh/feed.xml').read_text())
    assert not feed.bozo
    assert feed.feed.language == 'zh-CN'
    assert [entry.link for entry in feed.entries] == [f'{cfg.site.base_url}/zh/issues/{week}/' for week in ('2026-42', '2026-41')]
    assert '第 42 周：开发者工具。' in feed.entries[0].description
    assert '<script>' not in feed.entries[0].description
    assert '本期暂无中文版' in feed.entries[1].description


def test_partial_translation_falls_back_per_field(tmp_path: Path) -> None:
    data = json.loads((BILINGUAL / '2026-42.json').read_text())
    data['sixty_seconds_zh'] = [data['sixty_seconds_zh'][0], '']
    item = data['sections']['models'][0]
    item['zh'] = {'headline': '部分翻译'}
    source = tmp_path / 'issues'
    source.mkdir()
    (source / 'issue.json').write_text(json.dumps(data))
    render_site(load_config(), source, tmp_path / 'site')
    soup = BeautifulSoup((tmp_path / 'site/zh/index.html').read_text(), 'html.parser')
    card = soup.select_one('.card')
    assert card.h3.text == '部分翻译'
    assert item['summary'] in card.get_text()
    assert item['why_it_matters'] in card.get_text()
    assert item['for_builders'] in card.get_text()
    assert len(soup.select('.digest ol a')) == 3
    assert '本期暂无中文版' in soup.get_text()


def test_theme_text_contrast() -> None:
    """Check every CSS text/background pairing against the task's 4.5:1 floor."""
    import re

    css = (paths.ROOT / 'static/style.css').read_text()
    palettes = re.findall(r':root\s*\{([^}]+)\}', css)
    assert len(palettes) == 2

    def luminance(color: str) -> float:
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4
                  for channel in channels]
        return sum(channel * weight for channel, weight in zip(linear, (.2126, .7152, .0722)))

    pairs = [('digest-text', 'digest'), ('link', 'digest')]
    pairs += [(text, background) for text in ('text', 'muted', 'link')
              for background in ('background', 'card', 'surface')]
    pairs += [(section, 'background') for section in ('models', 'tools', 'github', 'quick')]
    for palette in palettes:
        colors = dict(re.findall(r'--([\w-]+):\s*(#[0-9a-f]{6})\s*;', palette))
        for foreground, background in pairs:
            light, dark = sorted([luminance(colors[foreground]), luminance(colors[background])], reverse=True)
            assert (light + .05) / (dark + .05) >= 4.5, (foreground, background)


@pytest.mark.parametrize('bilingual', [False, True])
def test_reader_labels_on_current_and_old_issues(tmp_path: Path, issue_fixtures: Path, bilingual: bool) -> None:
    out = tmp_path / 'site'
    render_site(load_config(), BILINGUAL if bilingual else issue_fixtures, out)
    for prefix, why, first_step in [('', "Why you'd care:", 'How to try it:'),
                                     ('zh/', '对你有什么用：', '怎么上手：')]:
        soup = BeautifulSoup((out / prefix / 'index.html').read_text(), 'html.parser')
        labels = [tag.text for tag in soup.select('article strong')]
        assert why in labels
        assert first_step in labels
        assert 'Why it matters:' not in labels
        assert 'For builders:' not in labels


@pytest.mark.parametrize('prefix', ['', 'zh/'])
def test_history_navigation_and_months(tmp_path: Path, prefix: str) -> None:
    from datetime import timedelta

    cfg = load_config(FIXTURES.parent / 'config.yaml')
    source, out = tmp_path / 'issues', tmp_path / 'site'
    source.mkdir()
    base = Issue.from_dict(json.loads((BILINGUAL / '2026-42.json').read_text()))
    for offset in range(9):
        delta = timedelta(weeks=offset)
        issue = replace(base, id=f'2026-{42 - offset}', period_start=base.period_start - delta,
                        period_end=base.period_end - delta, published_at=base.published_at - delta)
        (source / f'{issue.id}.json').write_text(json.dumps(issue.to_dict()))
    render_site(cfg, source, out)
    home = BeautifulSoup((out / prefix / 'index.html').read_text(), 'html.parser')
    rows = home.select('.past-issues .history-row > a')
    assert len(rows) == 6
    assert [a['href'].split('/')[-2] for a in rows] == [f'2026-{n}' for n in range(41, 35, -1)]
    assert all('🧠' in a.text for a in rows)
    assert home.select_one('.all-issues')['href'] == f'{cfg.base_path}/{prefix}archive/'
    assert len(home.select('.digest ol li a')) == 3
    assert len({card['id'] for card in home.select('article')}) == 15
    for link in home.select('.digest a'):
        target = home.find(id=link['href'].split('#')[1])
        assert link.text in target.text
    assert (out / prefix / 'index.html').stat().st_size + (out / 'assets/style.css').stat().st_size < 60_000
    for week, previous, following in [(42, 41, None), (38, 37, 39), (34, None, 35)]:
        page = BeautifulSoup((out / prefix / f'issues/2026-{week}/index.html').read_text(), 'html.parser')
        assert len(page.select('.issue-navigation')) == 2
        for rel, expected in [('prev', previous), ('next', following)]:
            links = page.select(f'.issue-navigation a[rel={rel}]')
            assert len(links) == (2 if expected else 0)
            assert all(a['href'] == f'{cfg.base_path}/{prefix}issues/2026-{expected}/' for a in links)
        assert '15' in page.select_one('.reading-time').text
    archive = BeautifulSoup((out / prefix / 'archive/index.html').read_text(), 'html.parser')
    groups = archive.select('.archive-month')
    assert len(groups) == 3
    assert len(archive.select('.history-row')) == 9
    assert len({group.h2.text for group in groups}) == 3
    assert not archive.select('.card, img')
    assert all(row.text.count('🧠') == 3 for row in archive.select('.history-row'))


@pytest.mark.parametrize('prefix', ['', 'zh/'])
def test_allowed_thumbnails_og_and_saved_bullet_targets(tmp_path: Path, prefix: str) -> None:
    cfg = load_config(FIXTURES.parent / 'config.yaml')
    issue = Issue.from_dict(json.loads((BILINGUAL / '2026-42.json').read_text()))
    by_key = {item.key: item for item in issue.items()}
    top = by_key[issue.top[0]]
    top.image_url = cfg.sources.github_image_url + '/org/repo'
    issue.top = list(by_key)[:3]
    issue.sixty_seconds_keys = [[key] for key in reversed(issue.top)]
    source = tmp_path / 'issues'
    source.mkdir()
    (source / 'issue.json').write_text(json.dumps(issue.to_dict()))
    render_site(cfg, source, tmp_path / 'site')
    page = BeautifulSoup((tmp_path / 'site' / prefix / 'index.html').read_text(), 'html.parser')
    assert not page.select('.issue-navigation')
    assert len(page.select('img')) == 1
    assert len(page.select('.image-band')) == 14
    assert page.select_one('meta[property="og:image"]')['content'] == top.image_url
    assert page.select_one('link[rel=icon]')['href'].startswith('data:image/svg+xml,')
    for link, keys in zip(page.select('.digest a'), issue.sixty_seconds_keys):
        card = page.find(id=link['href'].split('#')[1])
        item = by_key[keys[0]]
        assert ((item.zh or {}).get('headline') if prefix else item.headline) in card.h3.text
