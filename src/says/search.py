"""Full-text quote search over indexed transcript segments."""

from __future__ import annotations

import re
from dataclasses import dataclass

from says.models import SearchHit
from says.store import Store

_WORD = re.compile(r"[\w'-]+", re.UNICODE)


@dataclass(frozen=True)
class SearchFilters:
    perspectives: tuple[str, ...] = ()
    shows: tuple[str, ...] = ()
    speaker: str | None = None
    since: str | None = None  # ISO date (YYYY-MM-DD); compared against publish date


def build_match_query(text: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression.

    Each word becomes a quoted term so punctuation in user input cannot be read
    as FTS5 operators. Phrases in double quotes are kept as phrases. All terms
    must match (implicit AND).
    """
    parts: list[str] = []
    for phrase, loose in re.findall(r'"([^"]+)"|(\S+)', text):
        if phrase:
            words = _WORD.findall(phrase)
            if words:
                parts.append('"' + " ".join(words) + '"')
        else:
            parts.extend(f'"{w}"' for w in _WORD.findall(loose))
    if not parts:
        raise ValueError("query has no searchable words")
    return " ".join(parts)


def timestamp_url(audio_url: str | None, link: str | None, start: float) -> str | None:
    """Link to the moment a segment starts, using a W3C media fragment on the audio URL.

    Many players and browsers honor ``#t=<seconds>`` on direct media URLs. When
    there is no audio URL we fall back to the episode page with no fragment,
    because page URLs have no shared convention for seeking.
    """
    if audio_url:
        base = audio_url.split("#", 1)[0]
        return f"{base}#t={int(start)}"
    return link


def search(
    store: Store,
    query: str,
    *,
    filters: SearchFilters | None = None,
    limit: int = 20,
    raw: bool = False,
) -> list[SearchHit]:
    """Search segments. ``raw=True`` passes ``query`` to FTS5 unchanged."""
    filters = filters or SearchFilters()
    match = query if raw else build_match_query(query)
    sql = [
        """
        SELECT g.id AS segment_id, g.text, g.speaker, g.start_s, g.end_s,
               s.name AS show, s.perspective, e.title AS episode_title,
               e.published, e.link, e.audio_url, bm25(segments_fts) AS rank
        FROM segments_fts
        JOIN segments g ON g.id = segments_fts.rowid
        JOIN episodes e ON e.id = g.episode_id
        JOIN shows s ON s.id = e.show_id
        WHERE segments_fts MATCH ?
        """
    ]
    params: list[object] = [match]
    if filters.perspectives:
        sql.append(f"AND s.perspective IN ({','.join('?' * len(filters.perspectives))})")
        params.extend(filters.perspectives)
    if filters.shows:
        sql.append(f"AND s.name IN ({','.join('?' * len(filters.shows))})")
        params.extend(filters.shows)
    if filters.speaker:
        sql.append("AND g.speaker LIKE ?")
        params.append(f"%{filters.speaker}%")
    if filters.since:
        sql.append("AND e.published >= ?")
        params.append(filters.since)
    sql.append("ORDER BY rank LIMIT ?")
    params.append(limit)

    rows = store.conn.execute("\n".join(sql), params).fetchall()
    return [
        SearchHit(
            segment_id=r["segment_id"],
            quote=r["text"],
            speaker=r["speaker"],
            start=r["start_s"],
            end=r["end_s"],
            show=r["show"],
            perspective=r["perspective"],
            episode_title=r["episode_title"],
            episode_published=r["published"],
            source_url=r["link"] or r["audio_url"],
            timestamp_url=timestamp_url(r["audio_url"], r["link"], r["start_s"]),
            rank=r["rank"],
        )
        for r in rows
    ]


def group_by_perspective(hits: list[SearchHit]) -> dict[str, list[SearchHit]]:
    """Bucket hits by the user's perspective label, keeping rank order inside each bucket."""
    groups: dict[str, list[SearchHit]] = {}
    for hit in hits:
        groups.setdefault(hit.perspective or "untagged", []).append(hit)
    return groups
