# 0004: All quote output is capped; no full-transcript export

- Status: accepted
- Date: 2026-10-18

## Context

The tool stores full transcripts locally so they can be searched. The output
users take elsewhere should be short, attributed excerpts that point back to
the source, not copies of the source.

## Decision

- One function, `says.export.cap_quote`, shapes every quote that leaves the
  database through the CLI (search display and all export formats).
- Default cap is 280 characters, configurable via `settings.quote_max_chars`
  and `--max-chars`, with a hard ceiling of 1000 characters in code.
- Exports always include show, episode, publish date, speaker if known,
  perspective label if set, timestamp, and a link.
- There is no command that prints or exports a full transcript.

## Consequences

- Users needing more context must go to the source, which is the intended
  behavior.
- New export formats must call `cap_quote`; reviewers should check for this.
- The database file itself still contains full text. That is documented in
  docs/rights.md and protected by keeping it local and git-ignored.
