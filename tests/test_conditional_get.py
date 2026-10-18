"""Conditional GET for feeds. All HTTP goes through httpx.MockTransport; no network."""

import sqlite3
from functools import partial

import httpx
import pytest
from typer.testing import CliRunner

from says import cli, ingest
from says.feeds import FeedResponse, fetch_feed
from says.ingest import ingest_show
from says.store import SCHEMA_VERSION, Store

from conftest import COMMONS, FIXTURES, FakeFetcher

FEED_BODY = (FIXTURES / "feed_commons.xml").read_bytes()
LAST_MODIFIED = "Tue, 03 Mar 2026 14:00:00 GMT"


class FeedServer:
    """A tiny origin that honours If-None-Match and If-Modified-Since."""

    def __init__(self, etag: str | None = '"v1"', last_modified: str | None = LAST_MODIFIED):
        self.etag = etag
        self.last_modified = last_modified
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        headers = {}
        if self.etag:
            headers["ETag"] = self.etag
        if self.last_modified:
            headers["Last-Modified"] = self.last_modified
        inm = request.headers.get("If-None-Match")
        ims = request.headers.get("If-Modified-Since")
        if (inm and inm == self.etag) or (not inm and ims and ims == self.last_modified):
            return httpx.Response(304, headers=headers)
        return httpx.Response(200, headers=headers, content=FEED_BODY)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def server():
    return FeedServer()


# --- fetch_feed ------------------------------------------------------------


def test_first_fetch_is_unconditional_and_returns_validators(server):
    with server.client() as client:
        response = fetch_feed(COMMONS.feed_url, client=client)
    sent = server.requests[0].headers
    assert "If-None-Match" not in sent and "If-Modified-Since" not in sent
    assert response.content == FEED_BODY and not response.not_modified
    assert response.etag == '"v1"'
    assert response.last_modified == LAST_MODIFIED


def test_sends_validators_and_handles_304(server):
    with server.client() as client:
        response = fetch_feed(
            COMMONS.feed_url, etag='"v1"', last_modified=LAST_MODIFIED, client=client
        )
    sent = server.requests[0].headers
    assert sent["If-None-Match"] == '"v1"'
    assert sent["If-Modified-Since"] == LAST_MODIFIED
    assert response.not_modified and response.content is None
    assert (response.etag, response.last_modified) == ('"v1"', LAST_MODIFIED)


def test_304_without_validators_keeps_the_ones_sent():
    def handler(request):
        return httpx.Response(304)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        response = fetch_feed(COMMONS.feed_url, etag='"old"', last_modified="x", client=client)
    assert response.not_modified
    assert (response.etag, response.last_modified) == ('"old"', "x")


def test_last_modified_only(server):
    server.etag = None
    with server.client() as client:
        response = fetch_feed(COMMONS.feed_url, last_modified=LAST_MODIFIED, client=client)
    assert response.not_modified


def test_changed_feed_returns_new_body(server):
    server.etag = '"v2"'
    with server.client() as client:
        response = fetch_feed(COMMONS.feed_url, etag='"v1"', client=client)
    assert response.content == FEED_BODY and response.etag == '"v2"'


def test_http_errors_raise():
    def handler(request):
        return httpx.Response(500)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        fetch_feed(COMMONS.feed_url, client=client)


# --- ingest ----------------------------------------------------------------


def test_ingest_stores_validators_then_skips_unchanged_feed(store, server, monkeypatch):
    fetcher = FakeFetcher()
    with server.client() as client:
        feed_fetcher = partial(fetch_feed, client=client)
        first = ingest_show(store, COMMONS, fetcher=fetcher, feed_fetcher=feed_fetcher)
        assert first.episodes_new == 2 and not first.feed_unchanged
        show_id = store.show_id(COMMONS.feed_url)
        assert store.feed_validators(show_id) == ('"v1"', LAST_MODIFIED)

        def no_parse(_):
            raise AssertionError("feed must not be parsed on 304")

        monkeypatch.setattr(ingest.feeds, "parse_feed", no_parse)
        second = ingest_show(store, COMMONS, fetcher=fetcher, feed_fetcher=feed_fetcher)

    assert server.requests[1].headers["If-None-Match"] == '"v1"'
    assert second.feed_unchanged
    assert second.episodes_seen == 0 and second.errors == []
    assert "feed unchanged (304)" in second.summary()
    assert store.stats()["episodes"] == 2
    assert store.feed_validators(show_id) == ('"v1"', LAST_MODIFIED)


def test_unchanged_feed_still_retries_missing_transcripts(store, server):
    vtt = "https://media.example.com/commons/ep12.vtt"
    with server.client() as client:
        feed_fetcher = partial(fetch_feed, client=client)
        broken = FakeFetcher(extra={vtt: b"not vtt"})
        first = ingest_show(store, COMMONS, fetcher=broken, feed_fetcher=feed_fetcher)
        assert first.transcripts_provided == 0 and len(first.errors) == 1

        second = ingest_show(store, COMMONS, fetcher=FakeFetcher(), feed_fetcher=feed_fetcher)
    assert second.feed_unchanged
    assert second.transcripts_provided == 1
    assert store.stats()["transcripts"] == 1


def test_validators_cleared_when_server_stops_sending_them(store, server):
    with server.client() as client:
        feed_fetcher = partial(fetch_feed, client=client)
        ingest_show(store, COMMONS, fetcher=FakeFetcher(), feed_fetcher=feed_fetcher)
        server.etag = server.last_modified = None
        report = ingest_show(store, COMMONS, fetcher=FakeFetcher(), feed_fetcher=feed_fetcher)
    assert not report.feed_unchanged
    assert store.feed_validators(store.show_id(COMMONS.feed_url)) == (None, None)


def test_failed_fetch_keeps_previous_validators(store, server):
    with server.client() as client:
        ingest_show(
            store, COMMONS, fetcher=FakeFetcher(), feed_fetcher=partial(fetch_feed, client=client)
        )

    def failing(url, *, etag=None, last_modified=None):
        raise httpx.ConnectError("offline")

    report = ingest_show(store, COMMONS, fetcher=FakeFetcher(), feed_fetcher=failing)
    assert report.feed_failed and report.errors
    assert store.feed_validators(store.show_id(COMMONS.feed_url)) == ('"v1"', LAST_MODIFIED)


# --- schema migration ------------------------------------------------------


def test_version_1_database_is_migrated(tmp_path):
    path = tmp_path / "says.db"
    with Store(path) as store:
        ingest_show(store, COMMONS, fetcher=FakeFetcher())
    conn = sqlite3.connect(path)
    with conn:  # rewind to the 0.1.0 schema
        conn.execute("ALTER TABLE shows DROP COLUMN etag")
        conn.execute("ALTER TABLE shows DROP COLUMN last_modified")
        conn.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
    conn.close()

    with Store(path) as store:
        assert store.schema_version() == SCHEMA_VERSION == 2
        columns = {r["name"] for r in store.conn.execute("PRAGMA table_info(shows)")}
        assert {"etag", "last_modified"} <= columns
        assert store.stats()["episodes"] == 2
        show_id = store.show_id(COMMONS.feed_url)
        assert store.feed_validators(show_id) == (None, None)
    with Store(path) as store:  # reopening is a no-op
        assert store.schema_version() == SCHEMA_VERSION


def test_new_database_has_current_schema_version(store):
    assert store.schema_version() == SCHEMA_VERSION


# --- CLI -------------------------------------------------------------------


def test_cli_ingest_counts_unchanged_feeds(tmp_path, monkeypatch):
    monkeypatch.delenv("SAYS_DATABASE", raising=False)
    fake = FakeFetcher()
    responses = iter([FeedResponse(content=FEED_BODY, etag='"v1"'), FeedResponse(content=None)])
    seen: list[str | None] = []

    def feed_fetcher(url, *, etag=None, last_modified=None):
        seen.append(etag)
        return next(responses)

    monkeypatch.setattr(ingest.feeds, "fetch", fake)
    monkeypatch.setattr(ingest.feeds, "fetch_feed", feed_fetcher)
    config = tmp_path / "says.toml"
    config.write_text(
        f'[settings]\ndatabase = "says.db"\n[[show]]\nname = "{COMMONS.name}"\n'
        f'feed_url = "{COMMONS.feed_url}"\n'
    )
    runner = CliRunner()
    first = runner.invoke(cli.app, ["--config", str(config), "ingest"])
    assert first.exit_code == 0, first.output
    assert "1 feeds: 1 updated, 0 unchanged, 0 failed" in first.output
    second = runner.invoke(cli.app, ["--config", str(config), "ingest"])
    assert second.exit_code == 0, second.output
    assert "feed unchanged (304)" in second.output
    assert "1 feeds: 0 updated, 1 unchanged, 0 failed" in second.output
    assert seen == [None, '"v1"']
