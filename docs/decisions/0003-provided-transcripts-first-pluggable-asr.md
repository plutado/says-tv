# 0003: Prefer provided transcripts; local speech-to-text is an optional plugin

- Status: accepted
- Date: 2026-10-18

## Context

Many podcast feeds publish transcripts through the Podcasting 2.0
`podcast:transcript` tag. Others publish none. Local speech-to-text works well
but brings large dependencies, model downloads, and long run times, and a
default install should not require any of that.

## Decision

- Ingestion always tries publisher transcripts first, preferring timed formats
  (VTT, then SRT, then JSON).
- Local transcription runs only when requested with `--transcribe N` and a named
  backend.
- Backends implement a one-method protocol, `transcribe(path) -> list[Segment]`,
  and are registered by name. Their dependencies are imported only when the
  backend is constructed.
- faster-whisper is the first backend and is installed with
  `uv sync --extra whisper`. It is not a core dependency.
- Tests use a fake backend; the suite never loads a speech model.

## Consequences

- `uv sync` and `uv run pytest` stay fast and work offline.
- Additional backends (whisper.cpp, a remote endpoint the user runs themselves)
  can be added without touching the core.
- Untimed provided transcripts (plain text, HTML) are currently skipped, since
  quotes need timestamps. Indexing them with coarse positions is planned
  (ROADMAP M1).
