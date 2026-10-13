"""Strict, immutable configuration loaded from YAML."""
from dataclasses import MISSING, dataclass, fields, is_dataclass
from math import isfinite
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
class ImagesConfig:
    timeout_seconds: int = 10
    max_download_bytes: int = 5 * 1024 * 1024
    max_width: int = 640
    quality: int = 80
    target_bytes: int = 40 * 1024


@dataclass(frozen=True)
class SectionConfig:
    key: str
    title: str
    title_zh: str
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
    max_headline_chars: int
    sections: tuple[SectionConfig, ...]


@dataclass(frozen=True)
class ContentConfig:
    max_headline_chars_zh: int
    max_summary_words: int
    max_summary_chars_zh: int
    max_why_words: int
    max_why_chars_zh: int
    max_builders_words: int
    max_builders_chars_zh: int
    max_bullet_words: int
    max_bullet_chars_zh: int
    max_emoji_codepoints: int
    summarise_max_tokens: int


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
    timeout_seconds: float = 180
    max_retries: int = 2


@dataclass(frozen=True)
class DedupeConfig:
    title_similarity: float
    seen_retention_days: int


@dataclass(frozen=True)
class DiscordConfig:
    color: int
    languages: tuple[str, ...] = ("zh",)


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
    per_page: int
    max_text_chars: int
    include_prereleases: bool
    repos: tuple[ReleaseRepoConfig, ...]


@dataclass(frozen=True)
class GitHubTrendingConfig:
    name: str
    search_per_page: int
    snapshot_min_days: int
    snapshot_max_days: int
    snapshot_history_limit: int
    snapshot_retention_days: int
    created_within_days: int
    candidates: int
    exclude_repos: tuple[str, ...]
    queries: tuple[str, ...]


@dataclass(frozen=True)
class HackerNewsConfig:
    name: str
    api_url: str
    item_url: str
    hits_per_page: int
    min_points: int
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class RedditConfig:
    enabled: bool
    name: str
    api_url: str
    base_url: str
    subreddits: tuple[str, ...]
    limit: int
    min_score: int


@dataclass(frozen=True)
class SpacesConfig:
    enabled: bool
    api_url: str
    limit: int
    created_within_days: int


@dataclass(frozen=True)
class HuggingFaceConfig:
    name: str
    api_url: str
    base_url: str
    org_limit: int
    trending_limit: int
    created_within_days: int
    orgs: tuple[str, ...]
    repack_authors: tuple[str, ...]
    spaces: SpacesConfig


@dataclass(frozen=True)
class SourcesConfig:
    retries: int
    backoff_seconds: float
    github_api_url: str
    github_image_url: str
    github_api_version: str
    user_agent: str
    timeout_seconds: int
    primary_domains: tuple[str, ...]
    rss: tuple[RSSConfig, ...]
    html_index: HTMLIndexConfig
    github_releases: GitHubReleasesConfig
    github_trending: GitHubTrendingConfig
    hackernews: HackerNewsConfig
    huggingface: HuggingFaceConfig
    reddit: RedditConfig


@dataclass(frozen=True)
class Config:
    name: str
    name_zh: str
    tagline: str
    tagline_zh: str
    tags_zh: dict[str, str]
    content: ContentConfig
    publish_enabled: bool
    paused: bool
    site: SiteConfig
    issue: IssueConfig
    tags: dict[str, str]
    llm: LLMConfig
    dedupe: DedupeConfig
    discord: DiscordConfig
    sources: SourcesConfig
    images: ImagesConfig = ImagesConfig()

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
                if field.default is not MISSING:
                    result[field.name] = field.default
                    continue
                raise ConfigError(f"{child}: required key missing")
            result[field.name] = _convert(value[field.name], hints[field.name], child)
        return kind(**result)
    if get_origin(kind) is dict:
        if not isinstance(value, dict):
            raise ConfigError(f"{path}: expected mapping")
        key_type, value_type = get_args(kind)
        return {_convert(k, key_type, path): _convert(v, value_type, f"{path}.{k}")
                for k, v in value.items()}
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
    if (not cfg.discord.languages or len(set(cfg.discord.languages)) != len(cfg.discord.languages)
            or any(lang not in {'zh', 'en'} for lang in cfg.discord.languages)):
        raise ConfigError('discord.languages: expected a non-empty unique list of zh/en')
    if any(value <= 0 for value in vars(cfg.images).values()) or cfg.images.quality > 100:
        raise ConfigError('images: expected positive limits and quality <= 100')
    for name in ('tags', 'tags_zh'):
        labels = getattr(cfg, name)
        if set(labels) != {'try', 'learn', 'watch'} or any(not v.strip() for v in labels.values()):
            raise ConfigError(f'{name}: expected non-empty try, learn and watch labels')
    labels = {'name_zh': cfg.name_zh, 'tagline_zh': cfg.tagline_zh, **{
        f'tags_zh.{key}': value for key, value in cfg.tags_zh.items()}, **{
        f'issue.sections[{i}].title_zh': section.title_zh
        for i, section in enumerate(cfg.issue.sections)}}
    for path, value in labels.items():
        if not value.strip():
            raise ConfigError(f'{path}: must be non-empty')
    for key, value in vars(cfg.content).items():
        if value <= 0:
            raise ConfigError(f'content.{key}: must be a positive integer')
    image_url = urlsplit(cfg.sources.github_image_url)
    if image_url.scheme not in {'http', 'https'} or not image_url.hostname:
        raise ConfigError('sources.github_image_url: must be an http(s) URL')
    if cfg.issue.max_headline_chars <= 0:
        raise ConfigError("issue.max_headline_chars: must be a positive integer")
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
    if not isfinite(cfg.llm.timeout_seconds) or cfg.llm.timeout_seconds <= 0:
        raise ConfigError("llm.timeout_seconds: must be a positive finite number")
    if cfg.llm.max_retries <= 0:
        raise ConfigError("llm.max_retries: must be a positive integer")


def load_config(path: str | Path = "config.yaml") -> Config:
    try:
        with Path(path).open(encoding="utf-8") as stream:
            raw = yaml.safe_load(stream)
    except (OSError, UnicodeError, yaml.YAMLError):
        raise ConfigError("config: unable to read YAML configuration") from None
    cfg = _convert(raw, Config, "")
    _validate(cfg)
    return cfg
