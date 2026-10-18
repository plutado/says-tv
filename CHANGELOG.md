# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it reaches 1.0.

## [Unreleased]

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
