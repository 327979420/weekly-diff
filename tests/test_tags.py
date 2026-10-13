from weekly_diff.config import load_config
from weekly_diff.tags import tag_labels


def test_legacy_labels_both_languages() -> None:
    cfg = load_config()
    for labels in (cfg.tags, cfg.tags_zh):
        assert set(labels) == {'try', 'learn', 'watch'}
        mapped = tag_labels(labels)
        assert mapped['builders'] == labels['try']
        assert mapped['work'] == mapped['beginner'] == labels['learn']
        assert mapped['watch'] == labels['watch']
        assert set(labels) == {'try', 'learn', 'watch'}
