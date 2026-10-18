"""SQLite storage: shows, episodes, transcripts, timed segments, and an FTS5 index."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from says.models import FeedEpisode, Segment, ShowConfig

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shows (
    id              INTEGER PRIMARY KEY,
    feed_url        TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    perspective     TEXT,
    tags            TEXT NOT NULL DEFAULT '[]',
    feed_title      TEXT,
    last_fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS episodes (
    id               INTEGER PRIMARY KEY,
    show_id          INTEGER NOT NULL REFERENCES shows(id) ON DELETE CASCADE,
    guid             TEXT NOT NULL,
    title            TEXT NOT NULL,
    published        TEXT,
    link             TEXT,
    audio_url        TEXT,
    description      TEXT,
    duration_seconds REAL,
    transcript_url   TEXT,
    transcript_mime  TEXT,
    first_seen_at    TEXT NOT NULL,
    UNIQUE (show_id, guid)
);

CREATE TABLE IF NOT EXISTS transcripts (
    id           INTEGER PRIMARY KEY,
    episode_id   INTEGER NOT NULL UNIQUE REFERENCES episodes(id) ON DELETE CASCADE,
    source       TEXT NOT NULL CHECK (source IN ('provided', 'file', 'local_asr')),
    format       TEXT NOT NULL,
    origin       TEXT,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS segments (
    id            INTEGER PRIMARY KEY,
    episode_id    INTEGER NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
    transcript_id INTEGER NOT NULL REFERENCES transcripts(id) ON DELETE CASCADE,
    position      INTEGER NOT NULL,
    start_s       REAL NOT NULL,
    end_s         REAL NOT NULL,
    speaker       TEXT,
    text          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS segments_episode ON segments(episode_id, position);

CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    text,
    speaker,
    content = 'segments',
    content_rowid = 'id',
    tokenize = 'porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
    INSERT INTO segments_fts(rowid, text, speaker) VALUES (new.id, new.text, new.speaker);
END;

CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text, speaker)
    VALUES ('delete', old.id, old.text, old.speaker);
END;

CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
    INSERT INTO segments_fts(segments_fts, rowid, text, speaker)
    VALUES ('delete', old.id, old.text, old.speaker);
    INSERT INTO segments_fts(rowid, text, speaker) VALUES (new.id, new.text, new.speaker);
END;
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class EpisodeRow:
    id: int
    show_id: int
    guid: str
    title: str
    audio_url: str | None
    transcript_url: str | None
    transcript_mime: str | None
    has_transcript: bool


class Store:
    """Thin wrapper over a SQLite connection. Not thread-safe; one per process."""

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.conn:
            yield self.conn

    def _migrate(self) -> None:
        with self.transaction() as conn:
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT INTO meta(key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO NOTHING",
                (str(SCHEMA_VERSION),),
            )

    # --- shows -----------------------------------------------------------

    def sync_shows(self, shows: Iterable[ShowConfig]) -> None:
        """Make the shows table reflect the user's config (the source of truth for labels)."""
        with self.transaction() as conn:
            for show in shows:
                conn.execute(
                    """
                    INSERT INTO shows(feed_url, name, perspective, tags)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(feed_url) DO UPDATE SET
                        name = excluded.name,
                        perspective = excluded.perspective,
                        tags = excluded.tags
                    """,
                    (show.feed_url, show.name, show.perspective, json.dumps(list(show.tags))),
                )

    def show_id(self, feed_url: str) -> int | None:
        row = self.conn.execute("SELECT id FROM shows WHERE feed_url = ?", (feed_url,)).fetchone()
        return row["id"] if row else None

    def mark_fetched(self, show_id: int, feed_title: str | None) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE shows SET last_fetched_at = ?, feed_title = COALESCE(?, feed_title) "
                "WHERE id = ?",
                (_now(), feed_title, show_id),
            )

    # --- episodes --------------------------------------------------------

    def upsert_episode(
        self,
        show_id: int,
        episode: FeedEpisode,
        transcript_url: str | None,
        transcript_mime: str | None,
    ) -> tuple[int, bool]:
        """Insert or refresh an episode. Returns ``(episode_id, is_new)``."""
        existing = self.conn.execute(
            "SELECT id FROM episodes WHERE show_id = ? AND guid = ?", (show_id, episode.guid)
        ).fetchone()
        values = (
            episode.title,
            episode.published,
            episode.link,
            episode.audio_url,
            episode.description,
            episode.duration_seconds,
            transcript_url,
            transcript_mime,
        )
        with self.transaction() as conn:
            if existing:
                conn.execute(
                    """
                    UPDATE episodes SET title = ?, published = ?, link = ?, audio_url = ?,
                        description = ?, duration_seconds = ?, transcript_url = ?,
                        transcript_mime = ?
                    WHERE id = ?
                    """,
                    (*values, existing["id"]),
                )
                return existing["id"], False
            cur = conn.execute(
                """
                INSERT INTO episodes(show_id, guid, title, published, link, audio_url,
                    description, duration_seconds, transcript_url, transcript_mime, first_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (show_id, episode.guid, *values, _now()),
            )
            return int(cur.lastrowid or 0), True

    def episodes_without_transcript(self, show_id: int | None = None) -> list[EpisodeRow]:
        sql = _EPISODE_SELECT + " WHERE t.id IS NULL"
        params: tuple = ()
        if show_id is not None:
            sql += " AND e.show_id = ?"
            params = (show_id,)
        sql += " ORDER BY e.id"
        return [_episode_row(r) for r in self.conn.execute(sql, params)]

    def get_episode(self, episode_id: int) -> EpisodeRow | None:
        row = self.conn.execute(_EPISODE_SELECT + " WHERE e.id = ?", (episode_id,)).fetchone()
        return _episode_row(row) if row else None

    def find_episode(self, show_id: int, guid: str) -> EpisodeRow | None:
        row = self.conn.execute(
            _EPISODE_SELECT + " WHERE e.show_id = ? AND e.guid = ?", (show_id, guid)
        ).fetchone()
        return _episode_row(row) if row else None

    def list_episodes(self, limit: int = 50) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT e.id, s.name AS show, e.title, e.published,
                       t.source AS transcript_source,
                       (SELECT COUNT(*) FROM segments g WHERE g.episode_id = e.id) AS segments
                FROM episodes e
                JOIN shows s ON s.id = e.show_id
                LEFT JOIN transcripts t ON t.episode_id = e.id
                ORDER BY e.id DESC
                LIMIT ?
                """,
                (limit,),
            )
        )

    # --- transcripts and segments ---------------------------------------

    def replace_transcript(
        self, episode_id: int, segments: list[Segment], *, source: str, fmt: str, origin: str | None
    ) -> int:
        """Store a transcript for an episode, replacing any previous one."""
        with self.transaction() as conn:
            conn.execute("DELETE FROM transcripts WHERE episode_id = ?", (episode_id,))
            cur = conn.execute(
                "INSERT INTO transcripts(episode_id, source, format, origin, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (episode_id, source, fmt, origin, _now()),
            )
            transcript_id = int(cur.lastrowid or 0)
            conn.executemany(
                "INSERT INTO segments(episode_id, transcript_id, position, start_s, end_s, "
                "speaker, text) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (episode_id, transcript_id, i, s.start, s.end, s.speaker, s.text)
                    for i, s in enumerate(segments)
                ],
            )
        return transcript_id

    def stats(self) -> dict[str, int]:
        q = self.conn.execute
        return {
            "shows": q("SELECT COUNT(*) FROM shows").fetchone()[0],
            "episodes": q("SELECT COUNT(*) FROM episodes").fetchone()[0],
            "transcripts": q("SELECT COUNT(*) FROM transcripts").fetchone()[0],
            "segments": q("SELECT COUNT(*) FROM segments").fetchone()[0],
        }


_EPISODE_SELECT = """
SELECT e.id, e.show_id, e.guid, e.title, e.audio_url, e.transcript_url, e.transcript_mime,
       t.id IS NOT NULL AS has_transcript
FROM episodes e
LEFT JOIN transcripts t ON t.episode_id = e.id
"""


def _episode_row(row: sqlite3.Row) -> EpisodeRow:
    return EpisodeRow(
        id=row["id"],
        show_id=row["show_id"],
        guid=row["guid"],
        title=row["title"],
        audio_url=row["audio_url"],
        transcript_url=row["transcript_url"],
        transcript_mime=row["transcript_mime"],
        has_transcript=bool(row["has_transcript"]),
    )
