"""Parse timed transcripts (WebVTT, SRT, Podcasting 2.0 JSON) into segments."""

from __future__ import annotations

import json
import re
from pathlib import Path

from says.models import Segment

_TIMING = re.compile(
    r"(?P<start>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*(?P<end>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})"
)
_VOICE = re.compile(r"<v(?:\.[^\s>]+)*\s+([^>]+)>")
_TAG = re.compile(r"<[^>]+>")
# A leading "Name:" convention used by many SRT files. Kept short so ordinary
# sentences containing a colon are not mistaken for speaker labels.
_SPEAKER_PREFIX = re.compile(r"^([A-Z][\w.'-]*(?: [A-Z][\w.'-]*){0,3}):\s+(.*)$", re.DOTALL)


class TranscriptError(ValueError):
    """Raised when a transcript cannot be parsed."""


def parse_timestamp(value: str) -> float:
    """Convert ``HH:MM:SS.mmm`` / ``MM:SS.mmm`` / ``HH:MM:SS,mmm`` to seconds."""
    value = value.strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) not in (2, 3):
        raise TranscriptError(f"bad timestamp: {value!r}")
    try:
        numbers = [float(p) for p in parts]
    except ValueError as exc:
        raise TranscriptError(f"bad timestamp: {value!r}") from exc
    seconds = 0.0
    for n in numbers:
        seconds = seconds * 60 + n
    return seconds


def format_timestamp(seconds: float) -> str:
    """Render seconds as ``H:MM:SS`` (or ``MM:SS`` under an hour)."""
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def parse_vtt(text: str) -> list[Segment]:
    text = text.lstrip("﻿")
    if not text.lstrip().startswith("WEBVTT"):
        raise TranscriptError("missing WEBVTT header")
    return _parse_cues(text)


def parse_srt(text: str) -> list[Segment]:
    return _parse_cues(text.lstrip("﻿"))


def _parse_cues(text: str) -> list[Segment]:
    segments: list[Segment] = []
    blocks = re.split(r"\r?\n\s*\r?\n", text.replace("\r\n", "\n"))
    for block in blocks:
        lines = [line for line in block.split("\n") if line.strip()]
        timing_index = next((i for i, line in enumerate(lines) if _TIMING.search(line)), None)
        if timing_index is None:
            continue  # header, NOTE, STYLE, or stray text
        match = _TIMING.search(lines[timing_index])
        assert match is not None
        start = parse_timestamp(match["start"])
        end = parse_timestamp(match["end"])
        raw = "\n".join(lines[timing_index + 1 :])
        speaker, body = _split_speaker(raw)
        if body:
            segments.append(Segment(start=start, end=end, text=body, speaker=speaker))
    return segments


def _split_speaker(raw: str) -> tuple[str | None, str]:
    speaker = None
    voice = _VOICE.search(raw)
    if voice:
        speaker = voice.group(1).strip()
    body = _TAG.sub("", raw)
    body = " ".join(body.split())
    if speaker is None:
        prefix = _SPEAKER_PREFIX.match(body)
        if prefix:
            speaker, body = prefix.group(1), prefix.group(2).strip()
    return speaker, body


def parse_podcast_json(text: str) -> list[Segment]:
    """Parse the Podcasting 2.0 JSON transcript format."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TranscriptError(f"invalid JSON transcript: {exc}") from exc
    raw_segments = data.get("segments") if isinstance(data, dict) else None
    if not isinstance(raw_segments, list):
        raise TranscriptError("JSON transcript has no 'segments' list")
    segments = []
    for item in raw_segments:
        body = " ".join(str(item.get("body", "")).split())
        if not body or "startTime" not in item:
            continue
        start = float(item["startTime"])
        end = float(item.get("endTime", start))
        segments.append(Segment(start=start, end=end, text=body, speaker=item.get("speaker")))
    return segments


def merge_short_segments(segments: list[Segment], min_chars: int = 80) -> list[Segment]:
    """Join consecutive cues from the same speaker until they reach ``min_chars``.

    Caption files often split one sentence across several two-second cues,
    which makes search hits read as fragments. Merging keeps the earliest
    start time so citations still point at the moment the passage begins.
    """
    merged: list[Segment] = []
    for seg in segments:
        if merged and merged[-1].speaker == seg.speaker and len(merged[-1].text) < min_chars:
            prev = merged[-1]
            merged[-1] = Segment(
                start=prev.start, end=seg.end, text=f"{prev.text} {seg.text}", speaker=prev.speaker
            )
        else:
            merged.append(seg)
    return merged


FORMATS = {
    "vtt": parse_vtt,
    "srt": parse_srt,
    "json": parse_podcast_json,
}

_MIME_TO_FORMAT = {
    "text/vtt": "vtt",
    "application/x-subrip": "srt",
    "application/srt": "srt",
    "text/srt": "srt",
    "application/json": "json",
}


def format_for_mime(mime_type: str) -> str | None:
    return _MIME_TO_FORMAT.get(mime_type.lower())


def format_for_path(path: Path) -> str | None:
    suffix = path.suffix.lower().lstrip(".")
    return suffix if suffix in FORMATS else None


def parse_transcript(text: str, fmt: str) -> list[Segment]:
    try:
        parser = FORMATS[fmt]
    except KeyError as exc:
        raise TranscriptError(f"unsupported transcript format: {fmt}") from exc
    return parser(text)
