import json

from says.export import HARD_MAX_CHARS, cap_quote, export_json, export_markdown
from says.models import SearchHit


def make_hit(text="A short invented quote.", **kw):
    base = dict(
        segment_id=1,
        quote=text,
        speaker="Dana Example",
        start=75.25,
        end=82.0,
        show="The Example Commons Hour",
        perspective="left",
        episode_title="Ep. 12: Server Farms",
        episode_published="2026-03-03T14:00:00+00:00",
        source_url="https://commons.example.com/episodes/12",
        timestamp_url="https://media.example.com/commons/ep12.mp3#t=75",
        rank=-1.0,
    )
    base.update(kw)
    return SearchHit(**base)


def test_cap_quote_short_text_untouched():
    assert cap_quote("hello  world", 280) == ("hello world", False)


def test_cap_quote_cuts_on_word_boundary():
    text = "word " * 100
    quote, truncated = cap_quote(text, 50)
    assert truncated
    assert len(quote) <= 50
    assert quote.endswith("…")
    assert "wor…" not in quote


def test_cap_quote_hard_ceiling():
    quote, truncated = cap_quote("x " * 5000, 10_000)
    assert truncated
    assert len(quote) <= HARD_MAX_CHARS


def test_export_json_shape():
    data = json.loads(export_json([make_hit("y " * 400)], "water", 100))
    assert data["query"] == "water"
    assert data["quote_max_chars"] == 100
    r = data["results"][0]
    assert r["truncated"] is True and len(r["quote"]) <= 100
    assert r["timestamp"] == "01:15"
    assert r["perspective"] == "left"
    assert r["url"].endswith("#t=75")


def test_export_markdown():
    md = export_markdown([make_hit()], "water")
    assert md.startswith("# Quotes: water")
    assert "> A short invented quote." in md
    assert "[01:15](https://media.example.com/commons/ep12.mp3#t=75)" in md
    assert "(2026-03-03)" in md
    assert "`left`" in md


def test_export_markdown_unattributed_and_empty():
    md = export_markdown([make_hit(speaker=None, perspective=None, timestamp_url=None)], "q")
    assert "Unattributed speaker" in md
    assert "at 01:15" in md
    assert "No results." in export_markdown([], "q")
