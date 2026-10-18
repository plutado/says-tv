# says

says is a local-first podcast research tool. You give it the podcast feeds you
follow. It fetches new episodes, uses the transcript the publisher provides (or
transcribes the audio on your machine when there is none), and builds a
searchable index on your disk. Then you can ask: who said what about a topic,
on which episode, at what timestamp, across shows you have labeled by
perspective.

Results are short attributed quotes with the show, the episode, and a link to
the moment in the audio where the passage starts.

**Status: early development.** The pipeline from feed to search works for feeds
that publish transcripts, and for transcript files you import yourself. Local
transcription is wired in but lightly exercised. Expect the CLI and database
schema to change before 1.0. See [ROADMAP.md](ROADMAP.md).

## Who it is for

- Journalists sourcing quotes from experts and commentators across outlets.
- Researchers tracking how a topic is discussed over time and across shows.
- Newsletter writers who want to cite what was actually said, with a link back,
  instead of paraphrasing from memory.

The intended use is finding and citing short passages, then going back to the
source to listen in context. says is not a transcript reader or a podcast
archive.

## What says does not do

- It does not ship any podcast content, transcripts, or list of real shows. You
  supply your own feeds.
- It does not decide anyone's political leaning or rate claims. Perspective
  labels are free-form tags you assign per show in your own config. says
  filters and groups by them; it never infers them.
- It does not export full transcripts. Every quote it displays or exports is
  capped (280 characters by default). See [docs/rights.md](docs/rights.md).

## Built with

- Python 3.12+, managed with [uv](https://docs.astral.sh/uv/)
- SQLite with the FTS5 full-text extension (bundled with Python's `sqlite3`)
- httpx for fetching, defusedxml for parsing untrusted feed XML
- Typer for the CLI
- pytest and ruff
- Optional: faster-whisper for local speech-to-text

## Quick start

From a checkout of this repository:

```sh
uv sync

# Start a config from the example (the example feeds are fictional)
cp examples/says.example.toml says.toml

# Or add your own feeds, with your own perspective labels
uv run says feeds add https://your-feed-url/rss.xml --name "Some Show" --perspective center
uv run says feeds import-opml ~/Downloads/subscriptions.opml

# Fetch episodes and index any transcripts the publishers provide
uv run says ingest

# Search
uv run says search "data center water"
uv run says search '"zoning board"' --perspective left --perspective right --by-perspective
uv run says search grid --speaker "Dana" --since 2026-01-01

# Export short cited quotes
uv run says export "data center water" --format markdown -o quotes.md
uv run says export "data center water" --format json --max-chars 200

# Inspect what is stored
uv run says episodes
uv run says stats
```

If an episode has no published transcript, you can attach one you have on disk:

```sh
uv run says transcript import 42 ./my-notes/episode-42.vtt
```

### Local transcription (optional)

```sh
uv sync --extra whisper
uv run says ingest --transcribe 3 --transcriber faster-whisper
```

`--transcribe N` limits how many untranscribed episodes per show are processed
in one run. Audio is downloaded to `data/audio/` and deleted after transcription
unless you pass `--keep-audio`.

## Configuration

`says.toml` (git-ignored) holds your settings and feed list. See
[examples/says.example.toml](examples/says.example.toml) for every option.
`SAYS_CONFIG`, `SAYS_DATABASE`, `SAYS_AUDIO_CACHE`, and `SAYS_TRANSCRIBER`
override the corresponding settings; see [.env.example](.env.example).

All data lives in `data/says.db` by default. Delete that file to start over.

## Development

```sh
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
```

Tests use only invented feeds and transcripts under `tests/fixtures/`, and a
fake transcriber, so they need no network access and no speech model.

## Documentation

- [ROADMAP.md](ROADMAP.md): planned milestones and estimates
- [docs/system-design.md](docs/system-design.md): pipeline, data model, CLI
- [docs/rights.md](docs/rights.md): what is stored, what is exported, and why
- [docs/decisions/](docs/decisions/): architecture decision records
- [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md)

## License

MIT. See [LICENSE](LICENSE).
