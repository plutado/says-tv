# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it reaches 1.0.

## [Unreleased]

### Added

- `says doctor`: checks that the config loads, every feed entry has a
  well-formed http(s) URL, SQLite has FTS5, the database passes
  `PRAGMA integrity_check` and the FTS5 index matches its content table, the
  audio cache is writable, and the chosen transcriber's dependency imports.
  Prints one ok/warn/fail line per check and exits 1 on any failure.
- Conditional GET for feeds: the ETag and Last-Modified from each successful
  fetch are stored per show and sent as `If-None-Match` / `If-Modified-Since`
  next time. A 304 response is reported as "feed unchanged (304)" and the feed
  is not parsed. `says ingest` ends with a totals line of updated, unchanged,
  and failed feeds.

### Changed

- Database schema version 2 adds `shows.etag` and `shows.last_modified`.
  Version 1 databases are upgraded in place when opened.
- Provided transcripts are now retried for every stored episode that has an
  advertised transcript but none indexed, including when the feed is
  unchanged, rather than only for episodes in the latest feed response.

## [0.1.0] - 2026-10-18

### Added

- TOML config with per-show, user-assigned perspective labels and tags; OPML import.
- RSS 2.0 parsing with `podcast:transcript` detection and timed-format preference.
- Transcript parsers for WebVTT (with `<v>` speaker tags), SRT (with `Name:`
  prefixes), and Podcasting 2.0 JSON.
- SQLite store with an FTS5 index over transcript segments, kept in sync by triggers.
- Search with perspective, show, speaker, and date filters, and grouping by perspective.
- Markdown and JSON quote export with a configurable length cap and a hard ceiling.
- Pluggable transcriber interface; optional faster-whisper backend (`--extra whisper`).
- CLI: `feeds list|add|import-opml`, `ingest`, `episodes`, `transcript import`,
  `search`, `export`, `stats`.
- Tests over synthetic fixtures; CI running ruff and pytest via uv.
- Documentation: system design, rights posture, ADRs 0001 to 0004, roadmap.

[Unreleased]: https://github.com/plutado/says-tv/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/plutado/says-tv/releases/tag/v0.1.0
