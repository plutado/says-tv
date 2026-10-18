# says

[![CI](https://github.com/plutado/says-tv/actions/workflows/ci.yml/badge.svg)](https://github.com/plutado/says-tv/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)

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

## Example

This is real output from the current code. The two shows, their hosts and
guests, and every line of dialogue are the invented fixtures in
[tests/fixtures/](tests/fixtures/). For this run the fixture feeds were served
from a local `python -m http.server`, one show labeled `left` and one `right`
in `says.toml`. Audio links point at reserved example domains.

```console
$ says ingest
The Example Commons Hour: 2 episodes (2 new), 1 provided transcripts, 0 local transcripts
Fictional Frontier Report: 1 episodes (1 new), 1 provided transcripts, 0 local transcripts

$ says search "data center water" --by-perspective
== left ==
[00:01] Host Riley | The Example Commons Hour (left) | Ep. 12: Server Farms and the River
    "Welcome back to the Example Commons Hour. Today we are talking about data centers and water."
    https://media.example.com/commons/ep12.mp3#t=1
[01:15] Dana Example | The Example Commons Hour (left) | Ep. 12: Server Farms and the River
    "A large data center can draw as much water for cooling as a small town uses in summer."
    https://media.example.com/commons/ep12.mp3#t=75
== right ==
[02:10] Morgan Placeholder | Fictional Frontier Report (right) | Building Out the Desert
    "Data centers bring construction jobs first, and the tax base follows. Water recycling systems mean the cooling load is smaller than critics claim."
    https://cdn.example.org/frontier/desert.m4a?token=abc#t=130

$ says stats
shows        2
episodes     3
transcripts  2
segments     6
```

Each hit carries the speaker (from the publisher's transcript), the show and
your label for it, the episode, and an audio link with a `#t=` offset to the
moment the passage starts.

Export produces citable Markdown. Here the cap is lowered to 100 characters to
show truncation:

```console
$ says export cooling --format markdown --max-chars 100
```

```markdown
# Quotes: cooling

> A large data center can draw as much water for cooling as a small town uses in summer.
>
> Dana Example, *The Example Commons Hour*, "Ep. 12: Server Farms and the River" (2026-03-03), at [01:15](https://media.example.com/commons/ep12.mp3#t=75) `left`

> Data centers bring construction jobs first, and the tax base follows. Water recycling systems mean…
>
> Morgan Placeholder, *Fictional Frontier Report*, "Building Out the Desert" (2026-03-05), at [02:10](https://cdn.example.org/frontier/desert.m4a?token=abc#t=130) `right`
```

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

# Check the config, feeds, SQLite FTS5, database integrity, and transcriber
uv run says doctor
```

`says doctor` prints one `ok`, `warn`, or `fail` line per check and exits with
status 1 if any check fails. It never creates or changes the database.

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

## What's next

The full plan, with task-level estimates, is in [ROADMAP.md](ROADMAP.md).
Headline milestones, in working hours for one developer:

- **Reliable ingestion of provided transcripts** (12 to 16 h): conditional GET
  and backoff, polite per-host fetching, Atom and untimed text transcripts,
  a `says doctor` command (done).
- **Local transcription backends** (14 to 20 h): a fuller faster-whisper
  backend with word timestamps, a whisper.cpp backend, a transcript cache, and
  clear marking of ASR-derived quotes.
- **Speakers and guests** (14 to 20 h): guest names from show notes and
  `podcast:person`, optional diarization, and a `says speakers` command for
  naming speakers yourself.
- **Topics and better search** (12 to 18 h): context around hits, `NEAR` and
  exclusion terms, saved topic searches, optional semantic search.
- **Quote export formats** (8 to 12 h): CSV, citation templates, and a
  "balanced pull" that takes the top hits from each perspective label.
- **Local web UI** (16 to 24 h): a 127.0.0.1-only search page with
  side-by-side perspective columns and an audio player that seeks to the quote.
- **Operations and 1.0 hardening** (16 to 24 h): scheduled ingestion, schema
  migrations, packaging for `uv tool install`, parser fuzz tests, and a
  10,000-episode performance check.

Total remaining planned work is roughly 90 to 135 hours.

## Documentation

- [ROADMAP.md](ROADMAP.md): planned milestones and estimates
- [docs/system-design.md](docs/system-design.md): pipeline, data model, CLI
- [docs/rights.md](docs/rights.md): what is stored, what is exported, and why
- [docs/decisions/](docs/decisions/): architecture decision records
- [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md)

## License

MIT. See [LICENSE](LICENSE).
