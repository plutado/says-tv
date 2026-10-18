import pytest
from defusedxml import EntitiesForbidden

from says.feeds import FeedError, best_transcript, parse_duration, parse_feed


def test_parse_feed_reads_items_and_transcript_tags(fixtures):
    feed = parse_feed((fixtures / "feed_commons.xml").read_bytes())
    assert feed.title == "The Example Commons Hour"
    assert len(feed.episodes) == 2
    ep = feed.episodes[0]
    assert ep.guid == "commons-ep-12"
    assert ep.audio_url == "https://media.example.com/commons/ep12.mp3"
    assert ep.duration_seconds == 3723
    assert ep.published == "2026-03-03T14:00:00+00:00"
    assert "Dana Example" in (ep.description or "")
    assert [t.mime_type for t in ep.transcripts] == ["text/plain", "text/vtt"]


def test_best_transcript_prefers_timed_formats(fixtures):
    ep = parse_feed((fixtures / "feed_commons.xml").read_bytes()).episodes[0]
    link = best_transcript(ep.transcripts)
    assert link is not None
    assert link.mime_type == "text/vtt"
    assert link.language == "en"


def test_episode_without_transcript_tag(fixtures):
    ep = parse_feed((fixtures / "feed_commons.xml").read_bytes()).episodes[1]
    assert ep.transcripts == ()
    assert best_transcript(ep.transcripts) is None
    assert ep.duration_seconds == 2710


def test_guid_falls_back_to_enclosure():
    xml = """<rss><channel><title>t</title><item><title>x</title>
    <enclosure url="https://media.example.com/a.mp3"/></item></channel></rss>"""
    assert parse_feed(xml).episodes[0].guid == "https://media.example.com/a.mp3"


def test_rejects_non_rss():
    with pytest.raises(FeedError):
        parse_feed("<feed xmlns='http://www.w3.org/2005/Atom'></feed>")
    with pytest.raises(FeedError):
        parse_feed("not xml")


def test_rejects_entity_expansion():
    evil = """<?xml version="1.0"?>
    <!DOCTYPE r [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;">]>
    <rss><channel><title>&b;</title></channel></rss>"""
    with pytest.raises(EntitiesForbidden):
        parse_feed(evil)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("90", 90), ("01:30", 90), ("1:00:00", 3600), ("", None), ("abc", None), (None, None)],
)
def test_parse_duration(value, expected):
    assert parse_duration(value) == expected
