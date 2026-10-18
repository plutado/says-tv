import pytest

from says.config import ConfigError, append_shows, load_config, parse_opml
from says.models import ShowConfig


def test_missing_config_is_empty(tmp_path):
    cfg = load_config(tmp_path / "says.toml")
    assert cfg.shows == []
    assert cfg.settings.quote_max_chars == 280


def test_load_config(tmp_path):
    path = tmp_path / "says.toml"
    path.write_text(
        '[settings]\ndatabase = "x/says.db"\nquote_max_chars = 200\n\n'
        '[[show]]\nname = "A"\nfeed_url = "https://a.example.com/rss"\nperspective = "center"\n'
        'tags = ["energy"]\n'
    )
    cfg = load_config(path)
    assert cfg.settings.database == tmp_path / "x/says.db"
    assert cfg.settings.quote_max_chars == 200
    assert cfg.shows[0].perspective == "center"
    assert cfg.shows[0].tags == ("energy",)


@pytest.mark.parametrize(
    "body",
    [
        '[[show]]\nname = "A"\n',
        "[settings]\nquote_max_chars = 5\n",
        '[[show]]\nname="A"\nfeed_url="u"\n[[show]]\nname="B"\nfeed_url="u"\n',
        "not = [toml",
    ],
)
def test_bad_config(tmp_path, body):
    path = tmp_path / "says.toml"
    path.write_text(body)
    with pytest.raises(ConfigError):
        load_config(path)


def test_append_shows_round_trip(tmp_path):
    path = tmp_path / "says.toml"
    path.write_text("# my feeds\n")
    show = ShowConfig(
        name='Quote "Show"',
        feed_url="https://q.example.com/rss",
        perspective="left",
        tags=("a", "b"),
    )
    assert append_shows(path, [show]) == [show]
    assert append_shows(path, [show]) == []
    cfg = load_config(path)
    assert cfg.shows == [show]
    assert path.read_text().startswith("# my feeds\n")


def test_parse_opml(fixtures):
    shows = parse_opml((fixtures / "follows.opml").read_text(), default_perspective="mixed")
    assert [s.name for s in shows] == ["The Example Commons Hour", "Fictional Frontier Report"]
    assert all(s.perspective == "mixed" for s in shows)


def test_env_overrides_database(tmp_path, monkeypatch):
    monkeypatch.setenv("SAYS_DATABASE", str(tmp_path / "env.db"))
    assert load_config(tmp_path / "none.toml").settings.database == tmp_path / "env.db"
