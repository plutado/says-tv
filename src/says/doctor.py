"""Environment checks for ``says doctor``.

Each check returns a :class:`Check` with a status of ``ok``, ``warn``, or
``fail``. Checks never create or modify the database: a missing database is a
warning, and an existing one is opened without running the schema setup.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from says.config import Config, ConfigError, load_config
from says.store import SCHEMA_VERSION
from says.transcribe import check_backend

OK = "ok"
WARN = "warn"
FAIL = "fail"


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str

    def line(self) -> str:
        return f"{self.status:<4}  {self.name:<12} {self.detail}"


def run_checks(config_path: Path) -> list[Check]:
    """Run every check. Checks that need the config are skipped if it fails to load."""
    checks: list[Check] = []
    config: Config | None = None
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        checks.append(Check("config", FAIL, str(exc)))
    except OSError as exc:
        checks.append(Check("config", FAIL, f"{config_path}: {exc}"))
    else:
        if config_path.exists():
            checks.append(Check("config", OK, f"{config_path} ({len(config.shows)} shows)"))
        else:
            checks.append(Check("config", WARN, f"{config_path} not found; using defaults"))

    checks.append(check_fts5())

    if config is None:
        skipped = "skipped: config did not load"
        for name in ("feeds", "database", "audio cache", "transcriber"):
            checks.append(Check(name, WARN, skipped))
        return checks

    checks.extend(check_feeds(config))
    checks.extend(check_database(config.settings.database))
    checks.append(check_writable_dir("audio cache", config.settings.audio_cache))
    checks.append(check_transcriber(config.settings.transcriber))
    return checks


def has_failures(checks: list[Check]) -> bool:
    return any(c.status == FAIL for c in checks)


def check_feeds(config: Config) -> list[Check]:
    if not config.shows:
        return [Check("feeds", WARN, "no shows configured; add one with `says feeds add`")]
    checks: list[Check] = []
    for show in config.shows:
        problem = _feed_url_problem(show.feed_url)
        if problem:
            checks.append(Check("feed", FAIL, f"{show.name}: {problem}"))
        elif not show.perspective:
            checks.append(Check("feed", WARN, f"{show.name}: no perspective label"))
        else:
            checks.append(Check("feed", OK, f"{show.name} ({show.perspective})"))
    return checks


def _feed_url_problem(url: str) -> str | None:
    if url != url.strip() or any(ch.isspace() for ch in url):
        return f"feed_url contains whitespace: {url!r}"
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        return f"feed_url is not a valid URL: {exc}"
    if parts.scheme not in ("http", "https"):
        return f"feed_url must be http or https: {url!r}"
    if not parts.hostname:
        return f"feed_url has no host: {url!r}"
    return None


def check_fts5() -> Check:
    version = sqlite3.sqlite_version
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize = 'porter unicode61')")
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return Check("fts5", FAIL, f"SQLite {version} has no usable FTS5: {exc}")
    return Check("fts5", OK, f"SQLite {version} with FTS5")


def check_database(path: Path) -> list[Check]:
    if str(path) == ":memory:":
        return [Check("database", OK, "in-memory database")]
    if not path.exists():
        return [Check("database", WARN, f"{path} does not exist yet; `says ingest` creates it")]
    try:
        # mode=rw: open an existing file without creating one or running migrations.
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=rw", uri=True)
    except sqlite3.Error as exc:
        return [Check("database", FAIL, f"{path}: cannot open: {exc}")]
    try:
        return _inspect_database(conn, path)
    finally:
        conn.close()


def _inspect_database(conn: sqlite3.Connection, path: Path) -> list[Check]:
    checks: list[Check] = []
    try:
        rows = [r[0] for r in conn.execute("PRAGMA integrity_check")]
    except sqlite3.DatabaseError as exc:
        return [Check("database", FAIL, f"{path}: {exc}")]
    if rows != ["ok"]:
        summary = "; ".join(str(r) for r in rows[:3])
        return [Check("database", FAIL, f"{path}: integrity_check: {summary}")]

    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    version: int | None = None
    if "meta" in tables:
        row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        if row is not None:
            try:
                version = int(row[0])
            except ValueError:
                version = None
    if version is None:
        checks.append(Check("database", WARN, f"{path}: integrity ok, no schema version"))
    elif version > SCHEMA_VERSION:
        checks.append(
            Check(
                "database",
                FAIL,
                f"{path}: schema version {version} is newer than this says "
                f"supports ({SCHEMA_VERSION}); upgrade says",
            )
        )
    else:
        checks.append(Check("database", OK, f"{path}: integrity ok, schema version {version}"))

    if "segments_fts" in tables:
        try:
            # FTS5's own consistency check against the external content table.
            conn.execute(
                "INSERT INTO segments_fts(segments_fts, rank) VALUES ('integrity-check', 1)"
            )
        except sqlite3.DatabaseError as exc:
            checks.append(Check("fts index", FAIL, f"segments_fts: {exc}"))
        else:
            checks.append(Check("fts index", OK, "segments_fts matches segments"))
    else:
        checks.append(Check("fts index", WARN, "segments_fts table is missing"))
    return checks


def check_writable_dir(name: str, path: Path) -> Check:
    if path.exists():
        if not path.is_dir():
            return Check(name, FAIL, f"{path} exists and is not a directory")
        try:
            with tempfile.NamedTemporaryFile(dir=path, prefix=".says-doctor-"):
                pass
        except OSError as exc:
            return Check(name, FAIL, f"{path} is not writable: {exc}")
        return Check(name, OK, f"{path} is writable")
    parent = path.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    if parent.is_dir() and os.access(parent, os.W_OK | os.X_OK):
        return Check(name, OK, f"{path} will be created when needed")
    return Check(name, FAIL, f"{path} does not exist and {parent} is not writable")


def check_transcriber(name: str) -> Check:
    if not name or name == "none":
        return Check("transcriber", OK, "none (local transcription disabled)")
    try:
        detail = check_backend(name)
    except ValueError as exc:
        return Check("transcriber", FAIL, str(exc))
    except ImportError as exc:
        return Check("transcriber", FAIL, f"{name}: {exc}")
    return Check("transcriber", OK, detail)
