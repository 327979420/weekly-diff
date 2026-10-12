from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
import pytest

from weekly_diff.text import extract_main_text, extract_published_at, extract_title, html_to_text, parse_date

HTML = (Path(__file__).parent / 'fixtures/collectors/text.html').read_text()


def test_plain_text() -> None:
    text = html_to_text(HTML)
    assert 'Hello & world.' in text
    assert '<' not in text and 'secretScript' not in text and 'hiddenStyle' not in text
    assert extract_main_text(HTML) == 'News Hello & world.'


def test_title_precedence() -> None:
    assert extract_title(HTML) == 'Preferred & title'
    soup = BeautifulSoup(HTML, 'html.parser')
    soup.find('meta', property='og:title').decompose()
    assert extract_title(str(soup)) == 'Fallback & title'
    soup.title.decompose()
    assert extract_title(str(soup)) == ''


def test_date_precedence_and_json_graph() -> None:
    soup = BeautifulSoup(HTML, 'html.parser')
    assert extract_published_at(str(soup)) == datetime(2026, 10, 8, tzinfo=timezone.utc)
    soup.find('meta', property='article:published_time').decompose()
    assert extract_published_at(str(soup)) == datetime(2026, 10, 7, tzinfo=timezone.utc)
    soup.find('script', type='application/ld+json').string = 'invalid json'
    assert extract_published_at(str(soup)) == datetime(2026, 10, 6, tzinfo=timezone.utc)
    soup.time.decompose()
    assert extract_published_at(str(soup)) is None


@pytest.mark.parametrize('value', [None, '', 'not a date'])
def test_invalid_dates(value: str | None) -> None:
    assert parse_date(value) is None


def test_main_body_fallback() -> None:
    soup = BeautifulSoup(HTML, 'html.parser')
    soup.article.unwrap()
    assert extract_main_text(str(soup)) == 'Main News Hello & world.'
    soup.main.unwrap()
    assert extract_main_text(str(soup)) == 'Main News Hello & world. Date'
