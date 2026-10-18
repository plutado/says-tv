# Roadmap

Estimates are working hours for one developer, including tests and docs. They
are rough and will be revised as each milestone starts. Remaining planned work
(M1 to M8) is roughly 90 to 135 hours.

Milestone 0 is the current state of the repository.

## M0: Foundation (done)

- [x] Project layout, uv, ruff, pytest, CI
- [x] TOML config with user-assigned perspective labels; OPML import
- [x] RSS parsing with `podcast:transcript` detection and format preference
- [x] VTT, SRT, and Podcasting 2.0 JSON transcript parsing with speaker labels
- [x] SQLite store with FTS5 index kept in sync by triggers
- [x] Search with perspective, show, speaker, and date filters
- [x] Markdown and JSON quote export with a length cap
- [x] Pluggable transcriber interface with an optional faster-whisper backend
- [x] Tests over synthetic fixtures only

## M1: Reliable ingestion of provided transcripts (12 to 16 h)

Publisher transcripts are cheaper and usually more accurate than local
transcription, so they come first.

- [ ] Conditional GET (ETag / Last-Modified) and per-feed backoff (3 h)
- [ ] Polite fetching: per-host rate limit, timeouts, retry with jitter (2 h)
- [ ] Handle `podcast:transcript` with `rel="captions"` vs plain text; index
      untimed text/HTML transcripts with paragraph-level positions (3 h)
- [ ] Atom feed support and common RSS quirks (missing guid, relative URLs) (2 h)
- [ ] Episode-level transcript language selection (1 h)
- [ ] Test corpus of malformed synthetic feeds (2 h)
- [x] `says doctor` command: config check, FTS5 availability, DB integrity (1 h)

## M2: Local transcription backends (14 to 20 h)

- [ ] Streamed audio download with size limit and resume (2 h)
- [ ] faster-whisper backend: model size/device options in config, progress
      output, word timestamps for tighter quote boundaries (4 h)
- [ ] whisper.cpp backend via subprocess, for machines without PyTorch-class
      dependencies (4 h)
- [ ] Transcript cache keyed by audio hash so re-ingest never re-transcribes (2 h)
- [ ] Mark ASR-derived quotes in search and export output, since they may
      contain recognition errors (1 h)
- [ ] Integration test using generated audio (synthesized tones or TTS made at
      test time, never real episodes), skipped when the extra is not installed (3 h)

## M3: Speakers and guests (14 to 20 h)

Without speaker labels, many quotes are "unattributed". This milestone improves
attribution while keeping the user in control of names.

- [ ] Parse guest names from show notes using simple, inspectable patterns
      ("Guest:", "with ...", `podcast:person` tags) (4 h)
- [ ] Optional speaker diarization backend (for example pyannote) as a separate
      extra; produces anonymous speaker turns only (5 h)
- [ ] `says speakers` command to review and assign names to diarized speakers
      per episode, stored as user edits that survive re-ingest (4 h)
- [ ] Speaker aliases in config (same person, several spellings) (2 h)
- [ ] Clear labeling in output: "named by publisher", "named by user",
      "unnamed speaker 2" (1 h)

## M4: Topics and better search (12 to 18 h)

- [ ] Context window: show the segments before and after a hit (2 h)
- [ ] Phrase proximity (`NEAR`) and exclusion terms in the plain query syntax (2 h)
- [ ] Per-topic saved searches in config (for example "data centers" =
      several synonyms) (3 h)
- [ ] Topic extraction from show notes and transcripts using keyword statistics
      (TF-IDF over the user's own corpus), for browsing, not for labeling
      people (5 h)
- [ ] Optional embedding-based semantic search as a separate extra, with the
      FTS index remaining the default (5 h)

## M5: Quote export formats (8 to 12 h)

- [ ] CSV export for spreadsheets (1 h)
- [ ] Citation styles: plain, footnote-ready Markdown, and a configurable
      template (3 h)
- [ ] "Balanced pull": take the top N hits from each perspective label for a
      topic, so exports do not over-represent the most prolific show (3 h)
- [ ] Optional per-show link templates for publishers whose web players
      support a time parameter (2 h)
- [ ] Clipboard output (1 h)

## M6: Local web UI (16 to 24 h)

- [ ] Small local server (bound to 127.0.0.1 only) with search, filters, and
      side-by-side perspective columns (8 h)
- [ ] Embedded audio player that seeks to the quote timestamp (3 h)
- [ ] Collect quotes into a named "clip board" and export it (4 h)
- [ ] Speaker review screen for M3 (4 h)
- [ ] Basic accessibility pass: keyboard navigation, labels, contrast (2 h)

## M7: Scheduled ingestion and operations (8 to 12 h)

- [ ] `says ingest --since-last` with per-show schedules in config (2 h)
- [ ] Example launchd, systemd timer, and cron entries (2 h)
- [ ] Schema migrations with version checks and a backup-before-migrate step (3 h)
- [ ] Retention settings: drop segments for episodes older than N months (2 h)
- [ ] Package for `uv tool install` / pipx (1 h)

## M8: Hardening for 1.0 (8 to 12 h)

- [ ] Performance check on a synthetic corpus of 10,000 episodes (3 h)
- [ ] Fuzz tests for the VTT/SRT/feed parsers (2 h)
- [ ] Stable JSON export schema with a version field and docs (2 h)
- [ ] Review of docs/rights.md against actual behavior (1 h)
- [ ] User guide with worked research examples on synthetic data (2 h)

## Not planned

- Hosting or redistributing transcripts or audio.
- Automatic political or bias classification of shows, people, or claims.
- Fact-checking or truth scoring of quotes. A quote shows that something was
  said, not that it is correct.
