"""Presentation aliases for issues written before the vibe-coder tags."""


def tag_labels(labels: dict[str, str]) -> dict[str, str]:
    return {**labels, 'builders': labels['try'], 'work': labels['learn'],
            'beginner': labels['learn']}
