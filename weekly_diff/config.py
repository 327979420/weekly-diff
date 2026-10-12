"""Strict, immutable configuration loaded from YAML."""
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, get_args, get_origin, get_type_hints
from urllib.parse import urlsplit

import yaml


class ConfigError(ValueError):
    """Invalid configuration, identified by its key path."""


@dataclass(frozen=True)
class SiteConfig:
    base_url: str
    language: str
    timezone: str
    feed_items: int


@dataclass(frozen=True)
class SectionConfig:
    key: str
    title: str
    min: int
    max: int


@dataclass(frozen=True)
class IssueConfig:
    lookback_days: int
    min_items: int
    max_items: int
    hard_min_items: int
    top_items: int
    max_top_per_section: int
    sections: tuple[SectionConfig, ...]


@dataclass(frozen=True)
class TagsConfig:
    builders: str
    work: str
    beginner: str


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    anthropic_model: str
    openai_model: str
    effort: str
    max_candidates_to_score: int
    score_batch_size: int
    max_source_chars: int
    min_score: float


@dataclass(frozen=True)
class DedupeConfig:
    title_similarity: float
    seen_retention_days: int


@dataclass(frozen=True)
class DiscordConfig:
    color: int


@dataclass(frozen=True)
class RSSConfig:
    name: str
    url: str
    section: str


@dataclass(frozen=True)
class IndexPageConfig:
    name: str
    url: str
    link_pattern: str
    section: str


@dataclass(frozen=True)
class HTMLIndexConfig:
    max_articles_per_index: int
    pages: tuple[IndexPageConfig, ...]


@dataclass(frozen=True)
class ReleaseRepoConfig:
    name: str
    repo: str


@dataclass(frozen=True)
class GitHubReleasesConfig:
    include_prereleases: bool
    repos: tuple[ReleaseRepoConfig, ...]


@dataclass(frozen=True)
class GitHubTrendingConfig:
    created_within_days: int
    candidates: int
    max_stargazer_pages: int
    exclude_repos: tuple[str, ...]
    queries: tuple[str, ...]


@dataclass(frozen=True)
class HackerNewsConfig:
    min_points: int
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class HuggingFaceConfig:
    trending_limit: int
    created_within_days: int
    orgs: tuple[str, ...]


@dataclass(frozen=True)
class SourcesConfig:
    user_agent: str
    timeout_seconds: int
    primary_domains: tuple[str, ...]
    rss: tuple[RSSConfig, ...]
    html_index: HTMLIndexConfig
    github_releases: GitHubReleasesConfig
    github_trending: GitHubTrendingConfig
    hackernews: HackerNewsConfig
    huggingface: HuggingFaceConfig


@dataclass(frozen=True)
class Config:
    name: str
    tagline: str
    publish_enabled: bool
    paused: bool
    site: SiteConfig
    issue: IssueConfig
    tags: TagsConfig
    llm: LLMConfig
    dedupe: DedupeConfig
    discord: DiscordConfig
    sources: SourcesConfig

    @property
    def base_path(self) -> str:
        return urlsplit(self.site.base_url).path

    def issue_url(self, issue_id: str) -> str:
        return f"{self.site.base_url}/issues/{issue_id}/"


T = TypeVar("T")


def _convert(value: Any, kind: type[T], path: str) -> T:
    if is_dataclass(kind):
        if not isinstance(value, dict):
            raise ConfigError(f"{path}: expected mapping")
        hints = get_type_hints(kind)
        for key in value:
            if key not in hints:
                raise ConfigError(f"{path}.{key}: unknown key")
        result = {}
        for field in fields(kind):
            child = f"{path}.{field.name}" if path else field.name
            if field.name not in value:
                raise ConfigError(f"{child}: required key missing")
            result[field.name] = _convert(value[field.name], hints[field.name], child)
        return kind(**result)
    if get_origin(kind) is tuple:
        if not isinstance(value, list):
            raise ConfigError(f"{path}: expected list")
        element = get_args(kind)[0]
        return tuple(_convert(v, element, f"{path}[{i}]") for i, v in enumerate(value))
    if kind is float and type(value) in (int, float):
        return float(value)
    if type(value) is not kind:
        raise ConfigError(f"{path}: expected {kind.__name__}")
    return value


def _validate(cfg: Config) -> None:
    if cfg.site.base_url.endswith("/"):
        raise ConfigError("site.base_url: must not have a trailing slash")
    if cfg.issue.min_items > cfg.issue.max_items:
        raise ConfigError("issue.max_items: must be >= issue.min_items")
    keys: set[str] = set()
    for i, section in enumerate(cfg.issue.sections):
        if section.key in keys:
            raise ConfigError(f"issue.sections[{i}].key: duplicate section")
        keys.add(section.key)
        if section.min > section.max:
            raise ConfigError(f"issue.sections[{i}].max: must be >= min")
    if not {"models", "tools", "github", "quick"} <= keys:
        raise ConfigError("issue.sections: missing required section keys")
    if cfg.llm.provider not in {"auto", "anthropic", "openai"}:
        raise ConfigError("llm.provider: expected auto, anthropic or openai")


def load_config(path: str | Path = "config.yaml") -> Config:
    try:
        with Path(path).open(encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
    except (OSError, UnicodeError, yaml.YAMLError):
        raise ConfigError("config: unable to read YAML configuration") from None
    cfg = _convert(raw, Config, "")
    _validate(cfg)
    return cfg
