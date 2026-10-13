import pytest

from weekly_diff.shorten import shorten


@pytest.mark.parametrize(('text', 'limit', 'words', 'chinese', 'expected'), [
    ('You can build apps. More useful details follow here.', 7, True, False, 'You can build apps'),
    ('你可以构建应用。这里还有更多使用方法。', 12, False, True, '你可以构建应用'),
    ('You can build apps, with more useful details here.', 7, True, False, 'You can build apps'),
    ('Build useful apps today', 12, False, False, 'Build useful'),
    ('你可以构建有用的应用', 6, False, True, '你可以构建有'),
    ('Try tools (with extra details still coming)', 5, True, False, 'Try tools'),
    ('试用工具（还有更多详细说明）', 9, False, True, '试用工具'),
    ('Try (tools), then more details follow', 3, True, False, 'Try (tools)'),
    ('Try v2.1 with more details', 2, True, False, 'Try v2.1'),
    ('Already short.', 30, False, False, 'Already short.'),
])
def test_boundaries(text: str, limit: int, words: bool, chinese: bool, expected: str) -> None:
    assert shorten(text, limit, words=words, chinese=chinese) == expected
