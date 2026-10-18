# Content rights and design posture

This document explains what says stores, what it lets you export, and the
reasoning behind those limits. It describes the software's design, not legal
advice. Whether a particular use is fair use depends on the facts and the
jurisdiction, and the person publishing the quote is responsible for that
judgment.

## Summary

- The repository contains no podcast audio, transcripts, or list of real shows.
- You choose the feeds. says fetches only what those feeds publish publicly.
- Transcripts are stored locally, on your machine, for your own research.
- Exports are short quotes with attribution and a link back to the source.
  There is no command to export a full transcript.
- Perspective labels are yours. says does not classify people, shows, or claims.

## What is stored, and where

| Data | Stored? | Where |
|---|---|---|
| Feed metadata (titles, dates, links, show notes) | Yes | `data/says.db` |
| Transcript text, as timed segments | Yes | `data/says.db` |
| Original transcript files | No | Parsed into segments, then discarded |
| Audio | Only during local transcription, unless `--keep-audio` | `data/audio/` |

`data/` and `*.db` are git-ignored. Nothing is uploaded anywhere. Delete the
database to remove everything.

## Why store full transcripts at all

Search needs the text. Storing transcripts locally is the same kind of use as a
researcher keeping personal notes or a search index on their own computer. The
design keeps that copy private and makes redistribution of it awkward on
purpose:

- The database is local and not synced or served by says.
- The local web UI planned in the roadmap binds to 127.0.0.1 only.
- No export path returns more than a capped excerpt.

## Export limits

- Every quote shown by `says search` or written by `says export` passes through
  one function, `says.export.cap_quote`.
- The default cap is 280 characters (`settings.quote_max_chars`), and the
  `--max-chars` flag can change it per export.
- A hard ceiling of 1000 characters applies whatever the config says, so a typo
  cannot turn an export into a transcript dump.
- Truncated quotes end with an ellipsis and are flagged `"truncated": true` in
  JSON, so you know to check the source before publishing.
- Each quote includes the show, episode title, publish date, speaker (when
  known), and a timestamp link to the original audio. This supports
  attribution and sends readers to the publisher.

These limits are a design choice to support quotation for commentary,
criticism, and reporting. They are not a guarantee that any given use is
permitted.

## Provided transcripts first

Many publishers attach transcripts with the `podcast:transcript` tag. says uses
those before considering local transcription. They are the publisher's own
text, usually more accurate, and cost nothing to produce. Local transcription
is opt-in, per run, and limited by `--transcribe N`.

## Perspective labels

Shows are tagged in your config with whatever labels suit your work
(left/center/right, industry/advocacy, regional, or anything else). says:

- stores the label you wrote,
- filters and groups results by it,
- never infers, suggests, or modifies it,
- never assigns labels to individual speakers or to statements.

A label describes your sorting of a show, not a finding about a person.
Exports show the label so readers can see how you organized your sources.

## A quote is not a fact

says shows that a person said something on a particular episode at a particular
time. It does not check whether the statement is true, and it does not summarize
or paraphrase. ASR-derived text can contain recognition errors; always listen
to the source before quoting it publicly. (Marking ASR-derived quotes in output
is planned in ROADMAP M2.)

## Tests and fixtures

All feeds, shows, people, and dialogue in `tests/fixtures/` are invented and use
reserved example domains (example.com, example.org). Tests that need audio use a
fake transcriber and placeholder bytes. Contributions must follow the same rule:
do not add real podcast content to the repository.
