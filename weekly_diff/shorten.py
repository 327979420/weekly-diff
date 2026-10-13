"""Deterministic length repair without adding generated facts."""
import re
import unicodedata


def only_length_problems(problems: list[str]) -> bool:
    return bool(problems) and all(re.fullmatch(
        r'(?:zh\.)?\w+ exceeds \d+ (?:characters|words)', problem) for problem in problems)


def _clean(text: str) -> str:
    pairs = {'(': ')', '[': ']', '{': '}', '（': '）', '【': '】', '「': '」', '《': '》', '“': '”'}
    stack: list[tuple[str, int]] = []
    for index, char in enumerate(text):
        if char in pairs:
            stack.append((char, index))
        elif char in pairs.values():
            if stack and pairs[stack[-1][0]] == char:
                stack.pop()
            else:
                return _clean(text[:index])
    if stack:
        text = text[:stack[0][1]]
    text = text.rstrip()
    while text and unicodedata.category(text[-1]).startswith('P') and text[-1] not in pairs.values():
        text = text[:-1].rstrip()
    return text


def shorten(text: str, limit: int, *, words: bool = False, chinese: bool = False) -> str:
    """Prefer a complete clause, then a whole word or Chinese character cut."""
    tokens = list(re.finditer(r'\S+', text))
    if (len(tokens) if words else len(text)) <= limit:
        return text
    if words:
        end = tokens[limit - 1].end() if limit else 0
    elif chinese:
        end = limit
    else:
        ends = [token.end() for token in tokens if token.end() <= limit]
        end = ends[-1] if ends else 0
    # Do not split decimals, version numbers or punctuation inside identifiers.
    boundaries = [match.end() for match in re.finditer(r'[。！？；，]|[.!?;,](?=\s|$)', text)
                  if match.end() <= (end if words else limit)]
    for boundary in reversed(boundaries):
        if result := _clean(text[:boundary]):
            return result
    return _clean(text[:end])


def sentences(text: str) -> list[str]:
    """Extract complete sentences, preserving decimals, abbreviations and closers."""
    protected = re.sub(r'(?<=\d)\.(?=\d)', '\u2024', text)
    protected = re.sub(r'\b(?:e\.g\.|i\.e\.|Mr\.|Mrs\.|Dr\.|vs\.)',
                       lambda match: match.group().replace('.', '\u2024'), protected)
    ends = list(re.finditer(r'[。！？]|[.!?](?=[\"”’）)]*(?:\s|$))', protected))
    result = []
    start = 0
    for match in ends:
        end = match.end()
        while end < len(text) and text[end] in '\"”’）)':
            end += 1
        result.append(text[start:end].strip())
        start = end
    return result


def shorten_sentence(text: str, limit: int, *, words: bool = False) -> str:
    """After a rewrite retry, retain a full sentence even if it exceeds the budget."""
    if (len(text.split()) if words else len(text)) <= limit:
        return text
    complete = sentences(text)
    if not complete:
        return ''
    return complete[0]


def full_sentence(text: str) -> bool:
    return sentences(text) == [text.strip()]
