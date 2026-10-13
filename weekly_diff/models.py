"""JSON-compatible data exchanged by pipeline stages."""
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from typing import Any, Iterator, Literal, Self

from weekly_diff.dates import as_utc

SourceType = Literal["rss", "html_index", "github_release", "github_trending", "hackernews", "huggingface", "reddit"]


def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return as_utc(value).isoformat()
    if isinstance(value, dict):
        return {key: _encode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_encode(item) for item in value]
    return value


class JSONModel:
    def to_dict(self) -> dict[str, Any]:
        return _encode(asdict(self))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        values = dict(data)
        for field in fields(cls):
            if field.name in {"published_at", "period_start", "period_end"}:
                value = values[field.name]
                if value is not None:
                    values[field.name] = as_utc(datetime.fromisoformat(value))
        return cls(**values)


@dataclass
class Candidate(JSONModel):
    key: str
    title: str
    url: str
    source_name: str
    source_type: SourceType
    published_at: datetime | None
    text: str
    primary: bool
    section_hint: str | None
    signals: dict[str, float | int]
    extra: dict[str, Any]


@dataclass
class Item(JSONModel):
    key: str
    section: str
    headline: str
    summary: str
    why_it_matters: str
    for_builders: str | None
    tag: str
    source_url: str
    source_name: str
    published_at: datetime | None
    score: float
    extra: dict[str, Any]
    emoji: str | None = None
    zh: dict[str, str | None] | None = None
    image_url: str | None = None


@dataclass
class Issue(JSONModel):
    id: str
    name: str
    published_at: datetime
    period_start: datetime
    period_end: datetime
    sixty_seconds: list[str]
    sections: dict[str, list[Item]]
    top: list[str]
    sixty_seconds_zh: list[str] = field(default_factory=list)
    sixty_seconds_keys: list[list[str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        values = dict(data)
        values["sections"] = {
            section: [Item.from_dict(item) for item in items]
            for section, items in data["sections"].items()
        }
        return super().from_dict(values)

    def items(self) -> Iterator[Item]:
        for items in self.sections.values():
            yield from items
