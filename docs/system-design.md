# System design

This describes the code as it exists at 0.1.0.dev0. Planned changes are marked
as such and tracked in [ROADMAP.md](../ROADMAP.md).

## Goals and constraints

- Answer "who said what about X, on which episode, at what time" over feeds the
  user chose.
- Run entirely on the user's machine. No server, no account, no telemetry.
- Every result carries enough metadata to cite it and to find the moment in the
  original audio.
- Perspective is a user-owned label used as a query axis. The software does not
  produce it.
- Speech-to-text is optional. The core must install and run without it.

## Pipeline

```
 user config (says.toml / OPML)
        |
        v
 [1] feed fetch ----------> RSS XML (httpx, parsed with defusedxml)
        |
        v
 [2] episodes ------------> episodes table (deduplicated by show + guid)
        |
        +-- podcast:transcript present? --yes--> [3a] fetch provided VTT/SRT/JSON
        |                                              |
        no (and --transcribe N given)                  |
        |                                              |
        v                                              |
 [3b] download audio to cache -> local ASR backend     |
        |       (audio deleted afterwards by default)  |
        v                                              v
 [4] timed segments (start, end, speaker, text), short cues merged
        |
        v
 [5] segments table + segments_fts (FTS5, porter stemming, kept in sync by triggers)
        |
        v
 [6] search: FTS5 MATCH + filters (perspective, show, speaker, date), bm25 ranking
        |
        v
 [7] export: quote capped to quote_max_chars, plus show, episode, speaker,
     perspective label, timestamp, and a link with a #t= media fragment
```

### Stage notes

1. **Feed fetch** (`says.feeds`). One GET per feed. Feeds are untrusted input,
   so XML is parsed with defusedxml, which rejects entity declarations. Only
   RSS 2.0 is supported today.
2. **Episodes** (`says.store.Store.upsert_episode`). An episode is identified by
   `(show_id, guid)`. If the feed has no guid, the enclosure URL, then the
   link, then a hash of the title is used. `pubDate` is normalized to ISO 8601
   UTC so dates compare as text.
3. **Transcripts.**
   - (a) Provided: when an item has several `podcast:transcript` tags, says
     picks by format preference: VTT, then SRT, then JSON. Untimed formats
     (text/plain, text/html) are skipped for now, because a quote without a
     timestamp cannot be cited to a moment. An episode that already has a
     transcript is not re-fetched.
   - (b) Local: only when the user asks (`--transcribe N`) and a backend is
     configured. The backend interface is a single method,
     `transcribe(path) -> list[Segment]` (`says.transcribe.Transcriber`).
     Backends are registered by name and imported lazily.
   - (c) Manual: `says transcript import` attaches a file the user has.
4. **Segments** (`says.transcripts`). Caption files often split one sentence
   over several cues. Consecutive cues from the same speaker are merged until
   they reach about 80 characters, keeping the earliest start time. Speaker
   names come from VTT `<v Name>` tags, a leading `Name:` in SRT text, or the
   `speaker` field in JSON. Nothing is inferred beyond that.
5. **Index.** `segments_fts` is an external-content FTS5 table over
   `segments(text, speaker)`. Insert, update, and delete triggers keep it in
   sync. Replacing a transcript deletes its segments, which removes them from
   the index.
6. **Search** (`says.search`). Plain queries are rewritten so each word is a
   quoted FTS5 term and double-quoted phrases stay phrases. This prevents user
   punctuation from being parsed as FTS5 operators. `--raw` passes the query
   through unchanged for users who want FTS5 syntax.
7. **Export** (`says.export`). Every displayed or exported quote goes through
   `cap_quote`, which trims to the configured limit at a word boundary and
   enforces a hard ceiling of 1000 characters regardless of config.

## Data model

```
shows
  id, feed_url (unique), name, perspective, tags (JSON list),
  feed_title, last_fetched_at

episodes
  id, show_id -> shows, guid, title, published (ISO 8601), link, audio_url,
  description, duration_seconds, transcript_url, transcript_mime, first_seen_at
  unique (show_id, guid)

transcripts                      one per episode (replaced, not versioned)
  id, episode_id -> episodes (unique), source ('provided' | 'file' | 'local_asr'),
  format, origin (URL or path), created_at

segments
  id, episode_id -> episodes, transcript_id -> transcripts,
  position, start_s, end_s, speaker, text

segments_fts                     FTS5 external content over segments(text, speaker)

meta
  key, value                     currently only schema_version
```

`shows.name`, `perspective`, and `tags` are overwritten from the config on
every command. The config is the source of truth for labels; changing a label
in the config changes it in all future search results.

The raw transcript files are not stored; the segments are the stored form.
Audio is not stored unless the user passes `--keep-audio`.

## CLI surface

| Command | Purpose |
|---|---|
| `says feeds list` | Show configured shows and their labels |
| `says feeds add URL --name N [--perspective P] [--tag T]...` | Append a show to the config |
| `says feeds import-opml FILE [--perspective P]` | Append feeds from an OPML export |
| `says ingest [--show N] [--transcribe K] [--transcriber B] [--keep-audio]` | Fetch feeds, store episodes, index transcripts |
| `says episodes [--limit N]` | List episodes and transcript status |
| `says transcript import EPISODE_ID FILE [--format F]` | Attach a local VTT/SRT/JSON file |
| `says search QUERY [filters] [--by-perspective] [--raw]` | Print matching quotes with citations |
| `says export QUERY [-f markdown\|json] [-o FILE] [--max-chars N] [filters]` | Write cited quotes |
| `says stats` | Row counts |
| `says doctor` | Check config, feeds, FTS5, database integrity, audio cache, transcriber; exit 1 on any failure |

Filters shared by `search` and `export`: `--perspective/-p` (repeatable),
`--show` (repeatable), `--speaker` (substring), `--since YYYY-MM-DD`,
`--limit`.

`ingest` exits with status 2 when any feed or transcript failed, so scheduled
runs can alert on it.

## Timestamp links

Links use a W3C media fragment on the enclosure URL (`.../episode.mp3#t=75`).
Browsers and many players seek to that time when opening a direct media URL.
There is no shared convention for seeking on publisher web pages, so when an
episode has no enclosure the link points at the episode page without a time.
Per-show link templates are planned (ROADMAP M5).

## Module map

| Module | Responsibility |
|---|---|
| `says.config` | Load and append to the TOML config; OPML import |
| `says.feeds` | Fetch and parse RSS; pick a transcript link |
| `says.transcripts` | Parse VTT/SRT/JSON; merge short cues; time formatting |
| `says.store` | SQLite schema and queries |
| `says.ingest` | Orchestrates stages 1 to 5 |
| `says.transcribe` | Backend registry and the optional faster-whisper backend |
| `says.search` | Query building, filters, ranking |
| `says.export` | Quote capping and Markdown/JSON rendering |
| `says.doctor` | Read-only environment and database checks for `says doctor` |
| `says.cli` | Typer commands |

## Known limitations

- Audio downloads are read fully into memory before writing to the cache.
  Streaming download is planned (M2).
- Only one transcript per episode is kept; there is no history.
- No concurrency: feeds are fetched one after another.
- The `Name:` speaker heuristic for SRT can mislabel lines that begin with a
  capitalized word followed by a colon (for example "Note: ...").
- Schema migrations are not implemented yet; the schema is created if missing.
