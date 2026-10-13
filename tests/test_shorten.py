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


@pytest.mark.parametrize(('text', 'limit', 'words', 'expected'), [
    ('Useful tools. More details, and more details.', 3, True, 'Useful tools.'),
    ('工具可以使用。更多说明，如果你要跑很多小任务', 10, False, '工具可以使用。'),
    ('A complete sentence with more words than fit.', 3, True, 'A complete sentence with more words than fit.'),
    ('完整句子超过长度限制。后面的句子。', 3, False, '完整句子超过长度限制。'),
    ('Use v2.1, e.g. locally. Extra details follow.', 3, True, 'Use v2.1, e.g. locally.'),
    ('First clause, then an unfinished clause', 3, True, ''),
])
def test_sentence_only_shortening(text: str, limit: int, words: bool, expected: str) -> None:
    from weekly_diff.shorten import shorten_sentence
    assert shorten_sentence(text, limit, words=words) == expected
