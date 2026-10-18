import pytest

from says.transcripts import (
    TranscriptError,
    format_timestamp,
    merge_short_segments,
    parse_podcast_json,
    parse_srt,
    parse_timestamp,
    parse_vtt,
)


def test_parse_vtt_voice_tags(fixtures):
    segs = parse_vtt((fixtures / "commons_ep12.vtt").read_text())
    assert len(segs) == 5
    assert segs[2].speaker == "Dana Example"
    assert segs[2].start == pytest.approx(75.25)
    assert segs[2].text.startswith("A large data center")
    assert "<v" not in segs[2].text
    assert segs[4].start == 3605


def test_parse_vtt_requires_header():
    with pytest.raises(TranscriptError):
        parse_vtt("00:00:01.000 --> 00:00:02.000\nhello")


def test_parse_srt_speaker_prefix(fixtures):
    segs = parse_srt((fixtures / "frontier_desert.srt").read_text())
    speakers = [s.speaker for s in segs]
    assert speakers == ["Sam Fictional", "Morgan Placeholder", "Morgan Placeholder"]
    assert segs[1].start == 130
    assert segs[1].text.startswith("Data centers bring")


def test_parse_srt_without_speaker():
    segs = parse_srt("1\n00:00:01,000 --> 00:00:02,000\nplain words here\n")
    assert segs[0].speaker is None
    assert segs[0].text == "plain words here"


def test_parse_podcast_json_skips_blank(fixtures):
    segs = parse_podcast_json((fixtures / "sample_transcript.json").read_text())
    assert len(segs) == 2
    assert segs[0].speaker == "Avery Invented"
    assert segs[1].end == 12.0


def test_parse_podcast_json_errors():
    with pytest.raises(TranscriptError):
        parse_podcast_json("{")
    with pytest.raises(TranscriptError):
        parse_podcast_json('{"version": "1.0.0"}')


def test_merge_short_segments_keeps_first_start(fixtures):
    segs = parse_vtt((fixtures / "commons_ep12.vtt").read_text())
    merged = merge_short_segments(segs)
    assert merged[0].start == 1.0
    assert merged[0].end == 9.0
    assert "Welcome back" in merged[0].text and "data centers and water" in merged[0].text
    # different speaker is never merged
    assert merged[1].speaker == "Dana Example"


@pytest.mark.parametrize(
    ("raw", "seconds"),
    [("00:01.500", 1.5), ("01:02:03.000", 3723), ("00:00:02,250", 2.25)],
)
def test_parse_timestamp(raw, seconds):
    assert parse_timestamp(raw) == pytest.approx(seconds)


def test_format_timestamp():
    assert format_timestamp(75.9) == "01:15"
    assert format_timestamp(3723) == "1:02:03"
