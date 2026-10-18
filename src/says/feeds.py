"""RSS parsing, including detection of the Podcasting 2.0 ``podcast:transcript`` tag."""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC
from email.utils import parsedate_to_datetime

import httpx
from defusedxml import ElementTree as SafeET

from says.models import FeedEpisode, ParsedFeed, TranscriptLink

PODCAST_NS = "https://podcastindex.org/namespace/1.0"
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"

# Order of preference when a feed advertises several transcript formats.
# Timed formats come first because says needs timestamps to cite anything.
TRANSCRIPT_PREFERENCE = (
    "text/vtt",
    "application/x-subrip",
    "application/srt",
    "text/srt",
    "application/json",
)

USER_AGENT = "says/0.1 (+local podcast research tool)"


class FeedError(ValueError):
    """Raised when a document cannot be parsed as an RSS feed."""


@dataclass(frozen=True)
class FeedResponse:
    """Result of a conditional feed fetch.

    ``content`` is ``None`` when the server answered 304 Not Modified.
    ``etag`` and ``last_modified`` are the validators to send next time.
    """

    content: bytes | None
    etag: str | None = None
    last_modified: str | None = None

    @property
    def not_modified(self) -> bool:
        return self.content is None


def parse_feed(xml_text: str | bytes) -> ParsedFeed:
    """Parse RSS 2.0 text into a :class:`ParsedFeed`."""
    try:
        root = SafeET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise FeedError(f"not well-formed XML: {exc}") from exc
    channel = root.find("channel")
    if channel is None:
        raise FeedError("no <channel> element; only RSS 2.0 feeds are supported")

    episodes = [_parse_item(item) for item in channel.findall("item")]
    return ParsedFeed(
        title=_text(channel, "title"),
        link=_text(channel, "link"),
        episodes=[e for e in episodes if e is not None],
    )


def _parse_item(item: ET.Element) -> FeedEpisode | None:
    title = _text(item, "title") or "(untitled)"
    enclosure = item.find("enclosure")
    audio_url = enclosure.get("url") if enclosure is not None else None
    link = _text(item, "link")
    guid = _text(item, "guid") or audio_url or link
    if not guid:
        # Without any stable identifier we cannot de-duplicate across fetches.
        guid = "sha1:" + hashlib.sha1(title.encode("utf-8")).hexdigest()

    transcripts = tuple(
        TranscriptLink(
            url=el.get("url", ""),
            mime_type=(el.get("type") or "").lower(),
            language=el.get("language"),
            rel=el.get("rel"),
        )
        for el in item.findall(f"{{{PODCAST_NS}}}transcript")
        if el.get("url")
    )

    description = _text(item, f"{{{CONTENT_NS}}}encoded") or _text(item, "description")
    return FeedEpisode(
        guid=guid,
        title=title,
        published=normalize_date(_text(item, "pubDate")),
        link=link,
        audio_url=audio_url,
        description=description,
        duration_seconds=parse_duration(_text(item, f"{{{ITUNES_NS}}}duration")),
        transcripts=transcripts,
    )


def best_transcript(links: tuple[TranscriptLink, ...]) -> TranscriptLink | None:
    """Pick the most useful advertised transcript, preferring timed formats."""
    for mime in TRANSCRIPT_PREFERENCE:
        for link in links:
            if link.mime_type == mime:
                return link
    return None


def parse_duration(value: str | None) -> float | None:
    """Parse ``itunes:duration`` which may be seconds or ``[HH:]MM:SS``."""
    if not value:
        return None
    value = value.strip()
    try:
        parts = [float(p) for p in value.split(":")]
    except ValueError:
        return None
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def normalize_date(value: str | None) -> str | None:
    """Convert an RFC 822 ``pubDate`` to ISO 8601 so dates sort and compare as text.

    Unparseable values are kept as-is rather than dropped.
    """
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return value
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC)
    return parsed.isoformat(timespec="seconds")


def _text(parent: ET.Element, tag: str) -> str | None:
    el = parent.find(tag)
    if el is None or el.text is None:
        return None
    text = el.text.strip()
    return text or None


def fetch(url: str, client: httpx.Client | None = None, timeout: float = 30.0) -> bytes:
    """Fetch a URL and return the body. The caller owns retries and scheduling."""
    owns_client = client is None
    client = client or _client(timeout)
    try:
        response = client.get(url)
        response.raise_for_status()
        return response.content
    finally:
        if owns_client:
            client.close()


def _client(timeout: float) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def fetch_feed(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    client: httpx.Client | None = None,
    timeout: float = 30.0,
) -> FeedResponse:
    """Fetch a feed with a conditional GET.

    Sends ``If-None-Match`` / ``If-Modified-Since`` when validators from a
    previous fetch are given. A 304 response returns ``content=None`` and keeps
    the validators (updated if the server sent new ones).
    """
    headers: dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    owns_client = client is None
    client = client or _client(timeout)
    try:
        response = client.get(url, headers=headers)
        if response.status_code == httpx.codes.NOT_MODIFIED:
            return FeedResponse(
                content=None,
                etag=response.headers.get("ETag") or etag,
                last_modified=response.headers.get("Last-Modified") or last_modified,
            )
        response.raise_for_status()
        return FeedResponse(
            content=response.content,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
    finally:
        if owns_client:
            client.close()
