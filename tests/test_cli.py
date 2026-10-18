import json

import pytest
from typer.testing import CliRunner

from says import cli, ingest
from says.store import Store

from conftest import COMMONS, FRONTIER, FakeFetcher

runner = CliRunner()


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.delenv("SAYS_DATABASE", raising=False)
    fake = FakeFetcher()
    monkeypatch.setattr(ingest.feeds, "fetch", fake)
    monkeypatch.setattr(ingest.feeds, "fetch_feed", fake.feed)
    path = tmp_path / "says.toml"
    path.write_text('[settings]\ndatabase = "data/says.db"\nquote_max_chars = 60\n')
    return path


def run(config, *args):
    return runner.invoke(cli.app, ["--config", str(config), *args])


def test_full_flow(config, tmp_path):
    for show in (COMMONS, FRONTIER):
        result = run(
            config,
            "feeds",
            "add",
            show.feed_url,
            "--name",
            show.name,
            "--perspective",
            show.perspective,
        )
        assert result.exit_code == 0, result.output

    result = run(config, "feeds", "list")
    assert "(left)" in result.output and "(right)" in result.output

    result = run(config, "ingest")
    assert result.exit_code == 0, result.output
    assert "1 provided transcripts" in result.output

    result = run(config, "search", "data centers", "--by-perspective")
    assert result.exit_code == 0, result.output
    assert "== left ==" in result.output and "== right ==" in result.output
    assert "#t=" in result.output

    out = tmp_path / "quotes.json"
    result = run(config, "export", "water", "--format", "json", "--output", str(out))
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text())
    assert data["quote_max_chars"] == 60
    assert all(len(r["quote"]) <= 60 for r in data["results"])

    result = run(config, "stats")
    assert "segments" in result.output
    with Store(tmp_path / "data" / "says.db") as store:
        assert store.stats()["shows"] == 2


def test_search_with_no_words(config):
    result = run(config, "search", "()")
    assert result.exit_code == 1


def test_ingest_with_no_shows(config):
    result = run(config, "ingest")
    assert result.exit_code == 1
    assert "no matching shows" in result.output


def test_transcribe_requires_backend(config):
    run(config, "feeds", "add", COMMONS.feed_url, "--name", COMMONS.name)
    result = run(config, "ingest", "--transcribe", "1")
    assert result.exit_code == 1
    assert "backend" in result.output


def test_import_opml(config, fixtures):
    result = run(config, "feeds", "import-opml", str(fixtures / "follows.opml"))
    assert result.exit_code == 0
    assert "Imported 2 of 2" in result.output
    assert "untagged" in result.output


def test_version():
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0 and "says" in result.output


def test_raw_query_syntax_error_is_reported(config):
    run(config, "feeds", "add", COMMONS.feed_url, "--name", COMMONS.name)
    run(config, "ingest")
    result = run(config, "search", 'water AND ("', "--raw")
    assert result.exit_code == 1
    assert "search failed" in result.output
