"""Shared fixtures. All feeds and transcripts here are synthetic."""

from __future__ import annotations

from pathlib import Path

import pytest

from says.models import ShowConfig
from says.store import Store

FIXTURES = Path(__file__).parent / "fixtures"

COMMONS = ShowConfig(
    name="The Example Commons Hour",
    feed_url="https://feeds.example.com/commons.xml",
    perspective="left",
    tags=("environment",),
)
FRONTIER = ShowConfig(
    name="Fictional Frontier Report",
    feed_url="https://feeds.example.org/frontier.xml",
    perspective="right",
)

URL_MAP = {
    COMMONS.feed_url: "feed_commons.xml",
    FRONTIER.feed_url: "feed_frontier.xml",
    "https://media.example.com/commons/ep12.vtt": "commons_ep12.vtt",
    "https://cdn.example.org/frontier/desert.srt": "frontier_desert.srt",
}


class FakeFetcher:
    """Serves fixture files for known URLs and records every request."""

    def __init__(self, extra: dict[str, bytes] | None = None) -> None:
        self.calls: list[str] = []
        self.extra = extra or {}

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if url in self.extra:
            return self.extra[url]
        if url in URL_MAP:
            return (FIXTURES / URL_MAP[url]).read_bytes()
        raise RuntimeError(f"404 for {url}")


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def store(tmp_path: Path) -> Store:
    s = Store(tmp_path / "says.db")
    yield s
    s.close()


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher()
