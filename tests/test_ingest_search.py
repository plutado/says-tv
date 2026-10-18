from pathlib import Path

import pytest

from says.ingest import import_transcript_file, ingest_show
from says.models import Segment
from says.search import (
    SearchFilters,
    build_match_query,
    group_by_perspective,
    search,
    timestamp_url,
)

from conftest import COMMONS, FRONTIER, FakeFetcher


@pytest.fixture
def loaded(store, fetcher):
    ingest_show(store, COMMONS, fetcher=fetcher)
    ingest_show(store, FRONTIER, fetcher=fetcher)
    return store


def test_ingest_reports_and_stores(store, fetcher):
    report = ingest_show(store, COMMONS, fetcher=fetcher)
    assert report.episodes_seen == 2
    assert report.episodes_new == 2
    assert report.transcripts_provided == 1
    assert report.errors == []
    # the text/plain transcript is never requested; the VTT is preferred
    assert "https://media.example.com/commons/ep12.txt" not in fetcher.calls
    assert store.stats()["transcripts"] == 1


def test_ingest_is_idempotent(store, fetcher):
    ingest_show(store, COMMONS, fetcher=fetcher)
    again = ingest_show(store, COMMONS, fetcher=fetcher)
    assert again.episodes_new == 0
    assert again.transcripts_provided == 0  # already have it
    assert store.stats()["episodes"] == 2


def test_ingest_records_feed_errors(store):
    report = ingest_show(store, COMMONS, fetcher=FakeFetcher(extra={COMMONS.feed_url: b"<x"}))
    assert report.episodes_seen == 0
    assert report.errors and "feed" in report.errors[0]


def test_ingest_records_transcript_errors(store):
    bad = FakeFetcher(extra={"https://media.example.com/commons/ep12.vtt": b"not vtt"})
    report = ingest_show(store, COMMONS, fetcher=bad)
    assert report.transcripts_provided == 0
    assert len(report.errors) == 1


def test_search_returns_citation_fields(loaded):
    hits = search(loaded, "water cooling")
    assert hits
    top = hits[0]
    assert top.speaker == "Dana Example"
    assert top.show == "The Example Commons Hour"
    assert top.perspective == "left"
    assert top.episode_title == "Ep. 12: Server Farms and the River"
    assert top.start == pytest.approx(75.25)
    assert top.timestamp_url == "https://media.example.com/commons/ep12.mp3#t=75"
    assert top.source_url == "https://commons.example.com/episodes/12"


def test_search_spans_perspectives(loaded):
    hits = search(loaded, "data centers")
    groups = group_by_perspective(hits)
    assert set(groups) == {"left", "right"}


def test_search_filters(loaded):
    right = search(loaded, "data centers", filters=SearchFilters(perspectives=("right",)))
    assert right and all(h.perspective == "right" for h in right)
    by_speaker = search(loaded, "water", filters=SearchFilters(speaker="morgan"))
    assert by_speaker and all(h.speaker == "Morgan Placeholder" for h in by_speaker)
    by_show = search(loaded, "water", filters=SearchFilters(shows=("The Example Commons Hour",)))
    assert by_show and all(h.show == "The Example Commons Hour" for h in by_show)
    later = search(loaded, "data centers", filters=SearchFilters(since="2026-03-04"))
    assert later and all(h.show == "Fictional Frontier Report" for h in later)


def test_search_stemming(loaded):
    # porter tokenizer: "recycle" matches "recycling"
    assert search(loaded, "recycle")


def test_search_is_safe_with_fts_syntax(loaded):
    # unbalanced quotes and operators in user input must not raise
    assert isinstance(search(loaded, 'water AND ( "cooling'), list)
    assert build_match_query('"who gets a say" river-') == '"who gets a say" "river-"'
    with pytest.raises(ValueError):
        build_match_query("  ()  ")


def test_perspective_comes_from_config_not_data(store, fetcher):
    ingest_show(store, COMMONS, fetcher=fetcher)
    relabeled = COMMONS.__class__(
        name=COMMONS.name, feed_url=COMMONS.feed_url, perspective="center"
    )
    store.sync_shows([relabeled])
    assert search(store, "water")[0].perspective == "center"


def test_timestamp_url_fallbacks():
    assert (
        timestamp_url("https://m.example.com/a.mp3#old", None, 12.9)
        == "https://m.example.com/a.mp3#t=12"
    )
    assert timestamp_url(None, "https://example.com/ep", 5) == "https://example.com/ep"
    assert timestamp_url(None, None, 5) is None


def test_import_transcript_file(store, fetcher, fixtures):
    ingest_show(store, COMMONS, fetcher=fetcher)
    ep = store.find_episode(store.show_id(COMMONS.feed_url), "commons-ep-11")
    assert ep is not None and not ep.has_transcript
    count = import_transcript_file(store, ep.id, fixtures / "sample_transcript.json")
    assert count >= 1
    assert search(store, "zoning")[0].speaker == "Avery Invented"


def test_import_transcript_unknown_format(store, fetcher, tmp_path):
    ingest_show(store, COMMONS, fetcher=fetcher)
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    with pytest.raises(ValueError):
        import_transcript_file(store, 1, path)


def test_replacing_transcript_updates_index(store, fetcher):
    ingest_show(store, COMMONS, fetcher=fetcher)
    ep = store.find_episode(store.show_id(COMMONS.feed_url), "commons-ep-12")
    store.replace_transcript(
        ep.id, [Segment(0, 1, "entirely new words", "X")], source="file", fmt="vtt", origin=None
    )
    assert search(store, "river") == []
    assert search(store, "entirely new")


class FakeTranscriber:
    """Stands in for a speech-to-text backend; no audio is decoded."""

    name = "fake"

    def __init__(self):
        self.paths: list[Path] = []

    def transcribe(self, audio_path: Path) -> list[Segment]:
        self.paths.append(audio_path)
        assert audio_path.read_bytes() == b"fake-audio"
        return [Segment(3.0, 6.0, "Transmission lines are the real bottleneck.", None)]


def test_local_transcription_for_episodes_without_transcript(store, tmp_path):
    fetcher = FakeFetcher(extra={"https://media.example.com/commons/ep11.mp3": b"fake-audio"})
    backend = FakeTranscriber()
    report = ingest_show(
        store,
        COMMONS,
        fetcher=fetcher,
        transcriber=backend,
        audio_cache=tmp_path / "audio",
        max_transcribe=5,
    )
    assert report.transcripts_provided == 1
    assert report.transcripts_local == 1
    assert len(backend.paths) == 1
    assert not backend.paths[0].exists()  # audio removed unless keep_audio
    hit = search(store, "transmission bottleneck")[0]
    assert hit.episode_title == "Ep. 11: Grid Week"
    assert hit.speaker is None


def test_transcription_is_opt_in(store, fetcher, tmp_path):
    backend = FakeTranscriber()
    ingest_show(
        store,
        COMMONS,
        fetcher=fetcher,
        transcriber=backend,
        audio_cache=tmp_path / "audio",
        max_transcribe=0,
    )
    assert backend.paths == []
