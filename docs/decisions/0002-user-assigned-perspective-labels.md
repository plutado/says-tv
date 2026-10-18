# 0002: Perspective labels are user-assigned per show; no automated classification

- Status: accepted
- Date: 2026-10-18

## Context

A core use is sourcing a topic across perspectives, for example comparing what
left-, center-, and right-leaning shows said about data center construction.
That needs some perspective dimension in the data. Options:

1. Ship a curated list of shows with labels.
2. Infer labels with a model (from show descriptions, transcripts, or speakers).
3. Let the user assign a free-form label per show in their own config.

Shipping a list would put third-party show data in the repository and impose one
taxonomy on every user. Model-based inference would produce judgments about
real people and outlets that the software cannot justify, and errors would be
invisible to the user and to readers of anything they publish.

## Decision

Perspective is an optional free-form string per show in the user's config.
says stores it, filters by it, groups by it, and prints it in exports. It never
generates, suggests, or alters a label, and it never labels individual speakers
or statements.

## Consequences

- The labeling scheme is the user's responsibility and visible in exports.
- The same software serves other axes (industry vs. advocacy, local vs.
  national) without changes.
- The config is the source of truth: relabeling a show in the config updates
  every search result on the next command.
- Features that might be tempting later (per-speaker bias scores, claim
  slant) are out of scope by design. The roadmap lists this under "Not planned".
