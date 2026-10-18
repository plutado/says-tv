"""Ingestion pipeline: feed -> episodes -> transcript (provided or local ASR) -> segments."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from says import feeds
from says.models import ShowConfig
from says.store import Store
from says.transcribe import Transcriber
from says.transcripts import (
    TranscriptError,
    format_for_mime,
    format_for_path,
    merge_short_segments,
    parse_transcript,
)

Fetcher = Callable[[str], bytes]


class FeedFetcher(Protocol):
    """Fetches a feed, sending the validators from the previous fetch if any."""

    def __call__(
        self, url: str, *, etag: str | None = None, last_modified: str | None = None
    ) -> feeds.FeedResponse: ...


def _unconditional(fetcher: Fetcher) -> FeedFetcher:
    """Adapt a plain fetcher so it can fetch feeds (always a full 200 response)."""

    def fetch_feed(
        url: str, *, etag: str | None = None, last_modified: str | None = None
    ) -> feeds.FeedResponse:
        return feeds.FeedResponse(content=fetcher(url))

    return fetch_feed


@dataclass
class IngestReport:
    show: str
    episodes_seen: int = 0
    episodes_new: int = 0
    transcripts_provided: int = 0
    transcripts_local: int = 0
    feed_unchanged: bool = False
    feed_failed: bool = False
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        feed = (
            "feed unchanged (304)"
            if self.feed_unchanged
            else f"{self.episodes_seen} episodes ({self.episodes_new} new)"
        )
        parts = [
            f"{self.show}: {feed}",
            f"{self.transcripts_provided} provided transcripts",
            f"{self.transcripts_local} local transcripts",
        ]
        if self.errors:
            parts.append(f"{len(self.errors)} errors")
        return ", ".join(parts)


def ingest_show(
    store: Store,
    show: ShowConfig,
    *,
    fetcher: Fetcher | None = None,
    feed_fetcher: FeedFetcher | None = None,
    transcriber: Transcriber | None = None,
    audio_cache: Path | None = None,
    max_transcribe: int = 0,
    keep_audio: bool = False,
) -> IngestReport:
    """Fetch one show's feed, store its episodes, and attach transcripts.

    Provided transcripts (``podcast:transcript``) are always tried first. Local
    transcription runs only when a ``transcriber`` is given, and for at most
    ``max_transcribe`` episodes per call, because it is slow.

    The feed is fetched with a conditional GET using the ETag and Last-Modified
    saved from the previous fetch. On 304 Not Modified the feed is not parsed,
    but stored episodes still missing a provided transcript are retried.

    ``feed_fetcher`` fetches the feed; ``fetcher`` fetches transcripts and
    audio. If only ``fetcher`` is given it is used for the feed as well,
    without conditional headers.
    """
    if feed_fetcher is None:
        feed_fetcher = _unconditional(fetcher) if fetcher is not None else feeds.fetch_feed
    fetcher = fetcher or feeds.fetch
    report = IngestReport(show=show.name)
    store.sync_shows([show])
    show_id = store.show_id(show.feed_url)
    assert show_id is not None

    etag, last_modified = store.feed_validators(show_id)
    try:
        response = feed_fetcher(show.feed_url, etag=etag, last_modified=last_modified)
        parsed = None if response.not_modified else feeds.parse_feed(response.content or b"")
    except Exception as exc:  # network and parse errors are reported, not raised
        report.errors.append(f"feed {show.feed_url}: {exc}")
        report.feed_failed = True
        return report
    store.mark_fetched(
        show_id,
        parsed.title if parsed else None,
        etag=response.etag,
        last_modified=response.last_modified,
    )

    if parsed is None:
        report.feed_unchanged = True
    else:
        for episode in parsed.episodes:
            report.episodes_seen += 1
            link = feeds.best_transcript(episode.transcripts)
            _, is_new = store.upsert_episode(
                show_id,
                episode,
                transcript_url=link.url if link else None,
                transcript_mime=link.mime_type if link else None,
            )
            report.episodes_new += int(is_new)

    _fetch_provided_transcripts(store, show_id, report, fetcher)

    if transcriber is not None and max_transcribe > 0:
        _transcribe_missing(
            store,
            show_id,
            report,
            fetcher=fetcher,
            transcriber=transcriber,
            audio_cache=audio_cache or Path("data/audio"),
            limit=max_transcribe,
            keep_audio=keep_audio,
        )
    return report


def _fetch_provided_transcripts(
    store: Store, show_id: int, report: IngestReport, fetcher: Fetcher
) -> None:
    """Fetch advertised transcripts for stored episodes that do not have one yet."""
    for row in store.episodes_without_transcript(show_id):
        if not row.transcript_url or not row.transcript_mime:
            continue
        fmt = format_for_mime(row.transcript_mime)
        if fmt is None:
            continue
        try:
            text = fetcher(row.transcript_url).decode("utf-8", errors="replace")
            segments = merge_short_segments(parse_transcript(text, fmt))
        except Exception as exc:
            report.errors.append(f"transcript for {row.title!r}: {exc}")
            continue
        if segments:
            store.replace_transcript(
                row.id, segments, source="provided", fmt=fmt, origin=row.transcript_url
            )
            report.transcripts_provided += 1


def _transcribe_missing(
    store: Store,
    show_id: int,
    report: IngestReport,
    *,
    fetcher: Fetcher,
    transcriber: Transcriber,
    audio_cache: Path,
    limit: int,
    keep_audio: bool,
) -> None:
    pending = [e for e in store.episodes_without_transcript(show_id) if e.audio_url]
    for episode in pending[:limit]:
        assert episode.audio_url is not None
        audio_cache.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha1(episode.audio_url.encode()).hexdigest()
        audio_path = audio_cache / f"{name}{_suffix(episode.audio_url)}"
        try:
            if not audio_path.exists():
                audio_path.write_bytes(fetcher(episode.audio_url))
            segments = transcriber.transcribe(audio_path)
        except Exception as exc:
            report.errors.append(f"transcribe {episode.title!r}: {exc}")
            continue
        finally:
            if not keep_audio and audio_path.exists():
                audio_path.unlink()
        if segments:
            store.replace_transcript(
                episode.id,
                merge_short_segments(segments),
                source="local_asr",
                fmt=transcriber.name,
                origin=episode.audio_url,
            )
            report.transcripts_local += 1


def _suffix(url: str) -> str:
    tail = url.split("?", 1)[0].rsplit("/", 1)[-1]
    if "." in tail:
        ext = "." + tail.rsplit(".", 1)[-1].lower()
        if ext in {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac", ".mp4"}:
            return ext
    return ".audio"


def import_transcript_file(
    store: Store, episode_id: int, path: Path, fmt: str | None = None
) -> int:
    """Attach a transcript the user has on disk (for example, one they made themselves)."""
    if store.get_episode(episode_id) is None:
        raise ValueError(f"no episode with id {episode_id}")
    fmt = fmt or format_for_path(path)
    if fmt is None:
        raise TranscriptError(f"cannot tell transcript format from {path.name}; pass --format")
    segments = merge_short_segments(parse_transcript(path.read_text(encoding="utf-8"), fmt))
    if not segments:
        raise TranscriptError(f"{path} contains no timed segments")
    store.replace_transcript(episode_id, segments, source="file", fmt=fmt, origin=str(path))
    return len(segments)
