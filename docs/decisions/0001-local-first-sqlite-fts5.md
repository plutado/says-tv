# 0001: Local-first storage in a single SQLite file with FTS5

- Status: accepted
- Date: 2026-10-18

## Context

says indexes transcripts of podcasts a user follows. The corpus for one person
is likely thousands of episodes and a few million short segments. Users are
individuals (journalists, researchers, writers), not teams with servers. The
transcripts are third-party content that should stay on the user's machine
(see docs/rights.md).

Options considered:

1. SQLite with FTS5
2. A search server (Elasticsearch, OpenSearch, Meilisearch)
3. An embedded search library (Tantivy via bindings, Whoosh)
4. A vector database for semantic search

## Decision

Use one SQLite database file with an external-content FTS5 table over the
segments table, maintained by triggers. Use the `porter unicode61` tokenizer
and FTS5's built-in bm25 ranking.

## Consequences

- No service to run. Python's bundled `sqlite3` includes FTS5 on all common
  platforms, so `uv sync` is the whole install.
- Relational metadata (shows, episodes, perspective labels) and the text index
  live in one transaction scope. Filters by perspective or date are ordinary
  SQL joins.
- Backup and deletion are file operations, which keeps the privacy story simple.
- FTS5 does lexical matching only. Synonyms and semantic matches need either
  saved multi-term searches or an optional embedding index later (ROADMAP M4).
  That index, if added, must be optional and must not replace FTS5 as the
  default.
- Single writer. Fine for a CLI and a localhost UI; revisit if concurrent
  ingestion is added.
