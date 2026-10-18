import os
import sqlite3

import pytest
from typer.testing import CliRunner

from says import cli, doctor, transcribe
from says.doctor import FAIL, OK, WARN, run_checks
from says.ingest import ingest_show
from says.store import SCHEMA_VERSION, Store

from conftest import COMMONS, FakeFetcher

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("SAYS_DATABASE", "SAYS_AUDIO_CACHE", "SAYS_TRANSCRIBER"):
        monkeypatch.delenv(var, raising=False)


def write_config(tmp_path, body=""):
    path = tmp_path / "says.toml"
    path.write_text('[settings]\ndatabase = "data/says.db"\n' + body)
    return path


SHOW = '[[show]]\nname = "A"\nfeed_url = "https://a.example.com/rss"\nperspective = "left"\n'


def by_name(checks):
    return {c.name: c for c in checks}


def make_db(tmp_path):
    path = tmp_path / "data" / "says.db"
    with Store(path) as store:
        ingest_show(store, COMMONS, fetcher=FakeFetcher())
    return path


def test_healthy_setup(tmp_path):
    make_db(tmp_path)
    checks = run_checks(write_config(tmp_path, SHOW))
    statuses = {c.name: c.status for c in checks}
    assert statuses == {
        "config": OK,
        "fts5": OK,
        "feed": OK,
        "database": OK,
        "fts index": OK,
        "audio cache": OK,
        "transcriber": OK,
    }
    assert f"schema version {SCHEMA_VERSION}" in by_name(checks)["database"].detail
    assert not doctor.has_failures(checks)


def test_missing_config_and_database_are_warnings(tmp_path):
    checks = by_name(run_checks(tmp_path / "nope.toml"))
    assert checks["config"].status == WARN
    assert checks["feeds"].status == WARN
    assert checks["database"].status == WARN
    # doctor must not create the database
    assert not (tmp_path / "data" / "says.db").exists()


def test_invalid_config_fails_and_skips_dependent_checks(tmp_path):
    path = tmp_path / "says.toml"
    path.write_text("not = [toml")
    checks = by_name(run_checks(path))
    assert checks["config"].status == FAIL
    assert checks["fts5"].status == OK
    assert checks["database"].status == WARN
    assert "skipped" in checks["database"].detail


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("ftp://a.example.com/rss", "http or https"),
        ("https:///rss", "no host"),
        ("https://a.example.com/my feed.xml", "whitespace"),
        ("a.example.com/rss", "http or https"),
    ],
)
def test_malformed_feed_url_fails(tmp_path, url, expected):
    path = write_config(tmp_path, f'[[show]]\nname = "Bad"\nfeed_url = "{url}"\n')
    feed = by_name(run_checks(path))["feed"]
    assert feed.status == FAIL
    assert expected in feed.detail


def test_untagged_feed_warns(tmp_path):
    path = write_config(tmp_path, '[[show]]\nname = "A"\nfeed_url = "https://a.example.com/r"\n')
    assert by_name(run_checks(path))["feed"].status == WARN


def test_missing_fts5_fails(monkeypatch):
    class NoFts:
        def execute(self, sql):
            raise sqlite3.OperationalError("no such module: fts5")

        def close(self):
            pass

    monkeypatch.setattr(doctor.sqlite3, "connect", lambda *_a, **_k: NoFts())
    check = doctor.check_fts5()
    assert check.status == FAIL and "fts5" in check.detail


def test_corrupt_database_fails(tmp_path):
    path = make_db(tmp_path)
    data = bytearray(path.read_bytes())
    data[100 : len(data)] = b"\xff" * (len(data) - 100)
    path.write_bytes(bytes(data))
    checks = doctor.check_database(path)
    assert checks[0].status == FAIL


def test_not_a_database_fails(tmp_path):
    path = tmp_path / "data" / "says.db"
    path.parent.mkdir()
    path.write_bytes(b"this is not sqlite" * 100)
    assert doctor.check_database(path)[0].status == FAIL


def test_out_of_sync_fts_index_fails(tmp_path):
    path = make_db(tmp_path)
    conn = sqlite3.connect(path)
    with conn:
        conn.execute("DROP TRIGGER segments_ad")
        conn.execute("DELETE FROM segments WHERE id = (SELECT MIN(id) FROM segments)")
    conn.close()
    checks = by_name(doctor.check_database(path))
    assert checks["database"].status == OK
    assert checks["fts index"].status == FAIL


def test_newer_schema_version_fails(tmp_path):
    path = make_db(tmp_path)
    conn = sqlite3.connect(path)
    with conn:
        conn.execute(
            "UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION + 1),)
        )
    conn.close()
    check = by_name(doctor.check_database(path))["database"]
    assert check.status == FAIL and "newer" in check.detail


def test_audio_cache_checks(tmp_path):
    existing = tmp_path / "cache"
    existing.mkdir()
    assert doctor.check_writable_dir("audio cache", existing).status == OK
    assert list(existing.iterdir()) == []  # probe file is cleaned up
    assert doctor.check_writable_dir("audio cache", tmp_path / "a" / "b").status == OK
    a_file = tmp_path / "file"
    a_file.write_text("x")
    assert doctor.check_writable_dir("audio cache", a_file).status == FAIL


@pytest.mark.skipif(os.name != "posix" or os.geteuid() == 0, reason="needs non-root POSIX")
def test_unwritable_audio_cache_fails(tmp_path):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    try:
        assert doctor.check_writable_dir("audio cache", locked).status == FAIL
        assert doctor.check_writable_dir("audio cache", locked / "sub").status == FAIL
    finally:
        locked.chmod(0o700)


def test_transcriber_checks(monkeypatch):
    assert doctor.check_transcriber("none").status == OK
    unknown = doctor.check_transcriber("nonexistent")
    assert unknown.status == FAIL and "unknown transcriber" in unknown.detail

    monkeypatch.setitem(transcribe._REGISTRY, "fake", lambda: None)
    assert doctor.check_transcriber("fake").status == OK
    monkeypatch.setitem(
        transcribe._REQUIRED_MODULES, "fake", ("says_no_such_module", "uv sync --extra fake")
    )
    missing = doctor.check_transcriber("fake")
    assert missing.status == FAIL and "uv sync --extra fake" in missing.detail
    monkeypatch.setitem(transcribe._REQUIRED_MODULES, "fake", ("json", ""))
    assert doctor.check_transcriber("fake").status == OK


def test_cli_doctor_exit_codes(tmp_path):
    path = write_config(tmp_path, SHOW)
    result = runner.invoke(cli.app, ["--config", str(path), "doctor"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines and all(line.split()[0] in {OK, WARN} for line in lines)
    assert any(line.startswith("ok") and "fts5" in line for line in lines)

    path.write_text(path.read_text() + '\n[settings2]\n[[show]]\nname = "B"\nfeed_url = "x"\n')
    result = runner.invoke(cli.app, ["--config", str(path), "doctor"])
    assert result.exit_code == 1
    assert any(line.startswith("fail") for line in result.output.splitlines())
