"""Export search hits as short, attributed, cited quotes.

Every export path goes through :func:`cap_quote`. There is deliberately no
option to export a full transcript; see docs/rights.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from says.config import DEFAULT_QUOTE_MAX_CHARS
from says.models import SearchHit
from says.transcripts import format_timestamp

ELLIPSIS = "…"
HARD_MAX_CHARS = 1000


@dataclass(frozen=True)
class Citation:
    quote: str
    truncated: bool
    speaker: str | None
    show: str
    perspective: str | None
    episode: str
    published: str | None
    timestamp: str
    start_seconds: float
    url: str | None
    source_url: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "quote": self.quote,
            "truncated": self.truncated,
            "speaker": self.speaker,
            "show": self.show,
            "perspective": self.perspective,
            "episode": self.episode,
            "published": self.published,
            "timestamp": self.timestamp,
            "start_seconds": self.start_seconds,
            "url": self.url,
            "source_url": self.source_url,
        }


def cap_quote(text: str, max_chars: int = DEFAULT_QUOTE_MAX_CHARS) -> tuple[str, bool]:
    """Shorten ``text`` to at most ``max_chars`` characters, cutting at a word boundary.

    Returns ``(quote, truncated)``. ``max_chars`` is clamped to ``HARD_MAX_CHARS``
    so a config typo cannot turn exports into transcript dumps.
    """
    max_chars = max(20, min(max_chars, HARD_MAX_CHARS))
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text, False
    budget = max_chars - len(ELLIPSIS)
    cut = text[:budget]
    space = cut.rfind(" ")
    if space > budget // 2:
        cut = cut[:space]
    return cut.rstrip(" ,;:-") + ELLIPSIS, True


def to_citation(hit: SearchHit, max_chars: int = DEFAULT_QUOTE_MAX_CHARS) -> Citation:
    quote, truncated = cap_quote(hit.quote, max_chars)
    return Citation(
        quote=quote,
        truncated=truncated,
        speaker=hit.speaker,
        show=hit.show,
        perspective=hit.perspective,
        episode=hit.episode_title,
        published=hit.episode_published,
        timestamp=format_timestamp(hit.start),
        start_seconds=round(hit.start, 3),
        url=hit.timestamp_url,
        source_url=hit.source_url,
    )


def export_json(hits: list[SearchHit], query: str, max_chars: int = DEFAULT_QUOTE_MAX_CHARS) -> str:
    payload = {
        "query": query,
        "quote_max_chars": max_chars,
        "results": [to_citation(h, max_chars).to_dict() for h in hits],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def export_markdown(
    hits: list[SearchHit], query: str, max_chars: int = DEFAULT_QUOTE_MAX_CHARS
) -> str:
    lines = [f"# Quotes: {query}", ""]
    if not hits:
        lines.append("No results.")
        return "\n".join(lines) + "\n"
    for hit in hits:
        c = to_citation(hit, max_chars)
        lines.append(f"> {c.quote}")
        lines.append(">")
        who = c.speaker or "Unattributed speaker"
        where = f'*{_md_escape(c.show)}*, "{_md_escape(c.episode)}"'
        if c.published:
            where += f" ({c.published[:10]})"
        at = f"[{c.timestamp}]({c.url})" if c.url else c.timestamp
        tag = f" `{c.perspective}`" if c.perspective else ""
        lines.append(f"> {_md_escape(who)}, {where}, at {at}{tag}")
        lines.append("")
    return "\n".join(lines)


def _md_escape(text: str) -> str:
    return text.replace("[", "\\[").replace("]", "\\]").replace("*", "\\*")


EXPORTERS = {"markdown": export_markdown, "md": export_markdown, "json": export_json}
