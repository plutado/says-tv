# Contributing

Thanks for your interest. says is in early development, so open an issue to
discuss larger changes before writing code.

## Setup

```sh
uv sync
uv run pytest
uv run ruff check
uv run ruff format --check
```

CI runs the same commands on Python 3.12 and 3.13.

## Ground rules

- **No real podcast content.** Fixtures must be invented, using reserved
  domains such as example.com and example.org. Do not add real feeds,
  transcripts, audio, or show lists. If a test needs audio, generate it at test
  time or use the fake transcriber.
- **No automated classification of people or claims.** Perspective labels come
  only from the user's config. See docs/decisions/0002.
- **Quote output goes through `cap_quote`.** Any new display or export path must
  use it. See docs/decisions/0004.
- **Optional dependencies stay optional.** The core and the test suite must work
  without any speech-to-text library installed.

## Pull requests

- Keep changes focused and include tests.
- Update CHANGELOG.md under "Unreleased".
- Add an ADR in docs/decisions/ for decisions that change the data model, the
  rights posture, or a dependency.
