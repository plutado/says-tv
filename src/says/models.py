"""Plain data types shared across the pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ShowConfig:
    """A show the user follows, as written in their own config file.

    ``perspective`` is a free-form label the user assigns (for example "left",
    "center", "right", "industry", "academic"). says never infers it.
    """

    name: str
    feed_url: str
    perspective: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class TranscriptLink:
    """A transcript advertised by a feed via the ``podcast:transcript`` tag."""

    url: str
    mime_type: str
    language: str | None = None
    rel: str | None = None


@dataclass(frozen=True)
class FeedEpisode:
    """One item parsed from an RSS feed."""

    guid: str
    title: str
    published: str | None = None
    link: str | None = None
    audio_url: str | None = None
    description: str | None = None
    duration_seconds: float | None = None
    transcripts: tuple[TranscriptLink, ...] = ()


@dataclass(frozen=True)
class ParsedFeed:
    title: str | None
    link: str | None
    episodes: list[FeedEpisode] = field(default_factory=list)


@dataclass(frozen=True)
class Segment:
    """A timed span of transcript text. Times are in seconds."""

    start: float
    end: float
    text: str
    speaker: str | None = None


@dataclass(frozen=True)
class SearchHit:
    """One search result, carrying everything needed to cite it."""

    segment_id: int
    quote: str
    speaker: str | None
    start: float
    end: float
    show: str
    perspective: str | None
    episode_title: str
    episode_published: str | None
    source_url: str | None
    timestamp_url: str | None
    rank: float
