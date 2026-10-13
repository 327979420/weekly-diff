"""Editorial checks shared by item copy and highlights."""
import re

_BANNED = re.compile(
    r'赋能|助力|重磅|炸裂|全面升级|一站式|这意味着|\bgame-changer\b|'
    r'\brevolutionary\b|\bunlock\s+the\s+power\b|[!！]', re.I)


def banned_problems(text: str) -> list[str]:
    return ['banned phrase: ' + match.group() for match in _BANNED.finditer(text)]


def strip_banned(text: str) -> str:
    # Keep sentence boundaries when removing exclamation marks.
    text = text.replace('!', '.').replace('！', '。')
    return re.sub(r'[ \t]{2,}', ' ', _BANNED.sub('', text)).strip()


def opening(text: str, *, chinese: bool) -> str:
    text = text.strip().casefold()
    if chinese:
        return '你可以' if text.startswith('你可以') else text[:4]
    words = re.findall(r"\b[\w'-]+\b", text)
    return ' '.join(words[:2] if words[:2] == ['you', 'can'] else words[:4])
