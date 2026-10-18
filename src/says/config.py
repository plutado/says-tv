"""User configuration: the feeds they follow and how they tag them.

The config file is TOML and is owned by the user. says reads it and, for the
``feeds add`` and ``feeds import-opml`` commands, appends to it. It never
rewrites or reorders what the user wrote.

Example::

    [settings]
    database = "data/says.db"
    quote_max_chars = 280

    [[show]]
    name = "Example Policy Hour"
    feed_url = "https://feeds.example.com/policy-hour.xml"
    perspective = "center"
    tags = ["policy", "energy"]
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from defusedxml import ElementTree as SafeET

from says.models import ShowConfig

DEFAULT_CONFIG_PATH = Path("says.toml")
DEFAULT_DATABASE = Path("data/says.db")
DEFAULT_QUOTE_MAX_CHARS = 280


class ConfigError(ValueError):
    """Raised when the user's config file is malformed."""


@dataclass
class Settings:
    database: Path = DEFAULT_DATABASE
    quote_max_chars: int = DEFAULT_QUOTE_MAX_CHARS
    audio_cache: Path = Path("data/audio")
    transcriber: str = "none"


@dataclass
class Config:
    path: Path
    settings: Settings = field(default_factory=Settings)
    shows: list[ShowConfig] = field(default_factory=list)

    def show_by_feed(self, feed_url: str) -> ShowConfig | None:
        for show in self.shows:
            if show.feed_url == feed_url:
                return show
        return None


def resolve_config_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    env = os.environ.get("SAYS_CONFIG")
    return Path(env) if env else DEFAULT_CONFIG_PATH


def load_config(path: Path) -> Config:
    """Load a config file. A missing file yields an empty config."""
    if not path.exists():
        return Config(path=path, settings=_settings_from_env(Settings()))
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc

    settings = _parse_settings(raw.get("settings", {}), base=path.parent)
    shows = [_parse_show(entry, index) for index, entry in enumerate(raw.get("show", []))]
    seen: set[str] = set()
    for show in shows:
        if show.feed_url in seen:
            raise ConfigError(f"{path}: feed_url listed twice: {show.feed_url}")
        seen.add(show.feed_url)
    return Config(path=path, settings=_settings_from_env(settings), shows=shows)


def _parse_settings(raw: dict, base: Path) -> Settings:
    settings = Settings()
    if "database" in raw:
        settings.database = _relative_to(base, Path(raw["database"]))
    else:
        settings.database = _relative_to(base, DEFAULT_DATABASE)
    if "audio_cache" in raw:
        settings.audio_cache = _relative_to(base, Path(raw["audio_cache"]))
    else:
        settings.audio_cache = _relative_to(base, settings.audio_cache)
    if "quote_max_chars" in raw:
        value = raw["quote_max_chars"]
        if not isinstance(value, int) or value < 20:
            raise ConfigError("settings.quote_max_chars must be an integer >= 20")
        settings.quote_max_chars = value
    if "transcriber" in raw:
        settings.transcriber = str(raw["transcriber"])
    return settings


def _settings_from_env(settings: Settings) -> Settings:
    if db := os.environ.get("SAYS_DATABASE"):
        settings.database = Path(db)
    if cache := os.environ.get("SAYS_AUDIO_CACHE"):
        settings.audio_cache = Path(cache)
    if transcriber := os.environ.get("SAYS_TRANSCRIBER"):
        settings.transcriber = transcriber
    return settings


def _relative_to(base: Path, path: Path) -> Path:
    return path if path.is_absolute() else base / path


def _parse_show(entry: dict, index: int) -> ShowConfig:
    if not isinstance(entry, dict):
        raise ConfigError(f"show #{index + 1} is not a table")
    name = entry.get("name")
    feed_url = entry.get("feed_url")
    if not name or not feed_url:
        raise ConfigError(f"show #{index + 1} needs both 'name' and 'feed_url'")
    tags = entry.get("tags", [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        raise ConfigError(f"show {name!r}: 'tags' must be a list of strings")
    perspective = entry.get("perspective")
    return ShowConfig(
        name=str(name),
        feed_url=str(feed_url),
        perspective=str(perspective) if perspective else None,
        tags=tuple(tags),
    )


def show_to_toml(show: ShowConfig) -> str:
    """Render a show as a TOML ``[[show]]`` table for appending to a config."""
    lines = ["[[show]]", f"name = {_toml_str(show.name)}", f"feed_url = {_toml_str(show.feed_url)}"]
    if show.perspective:
        lines.append(f"perspective = {_toml_str(show.perspective)}")
    if show.tags:
        lines.append("tags = [" + ", ".join(_toml_str(t) for t in show.tags) + "]")
    return "\n".join(lines) + "\n"


def append_shows(path: Path, shows: list[ShowConfig]) -> list[ShowConfig]:
    """Append shows not already present. Returns the shows actually added."""
    existing = load_config(path)
    known = {s.feed_url for s in existing.shows}
    added = [s for s in shows if s.feed_url not in known]
    if not added:
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = ""
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current and not current.endswith("\n"):
            prefix = "\n"
        prefix += "\n" if current.strip() else ""
    with path.open("a", encoding="utf-8") as fh:
        fh.write(prefix + "\n".join(show_to_toml(s) for s in added))
    return added


def _toml_str(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\t", "\\t")
    return f'"{escaped}"'


def parse_opml(text: str, default_perspective: str | None = None) -> list[ShowConfig]:
    """Extract feed outlines from an OPML export.

    Perspective is not present in OPML; the user can pass one default for the
    whole file or edit the config afterwards.
    """
    root = SafeET.fromstring(text)
    shows: list[ShowConfig] = []
    for outline in root.iter("outline"):
        url = outline.get("xmlUrl")
        if not url:
            continue
        name = outline.get("title") or outline.get("text") or url
        shows.append(ShowConfig(name=name, feed_url=url, perspective=default_perspective))
    return shows
