"""Command-line interface."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from says import __version__
from says.config import (
    Config,
    ConfigError,
    append_shows,
    load_config,
    parse_opml,
    resolve_config_path,
)
from says.export import EXPORTERS, cap_quote
from says.ingest import import_transcript_file, ingest_show
from says.models import ShowConfig
from says.search import SearchFilters, group_by_perspective, search
from says.store import Store
from says.transcribe import TranscriberUnavailable, get_transcriber
from says.transcripts import TranscriptError, format_timestamp

app = typer.Typer(
    help="Search who said what across the podcasts you follow.",
    no_args_is_help=True,
    add_completion=False,
)
feeds_app = typer.Typer(help="Manage the feeds in your config file.", no_args_is_help=True)
transcript_app = typer.Typer(help="Attach transcripts manually.", no_args_is_help=True)
app.add_typer(feeds_app, name="feeds")
app.add_typer(transcript_app, name="transcript")


@dataclass
class State:
    config_path: Path

    def config(self) -> Config:
        try:
            return load_config(self.config_path)
        except ConfigError as exc:
            _fail(str(exc))
            raise  # unreachable; keeps type checkers happy

    def store(self, config: Config | None = None) -> Store:
        config = config or self.config()
        store = Store(config.settings.database)
        store.sync_shows(config.shows)
        return store


def _fail(message: str, code: int = 1) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"says {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Config file (default: $SAYS_CONFIG or ./says.toml)."),
    ] = None,
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version, is_eager=True, help="Show version and exit."),
    ] = False,
) -> None:
    ctx.obj = State(config_path=resolve_config_path(config))


# --- feeds ---------------------------------------------------------------


@feeds_app.command("list")
def feeds_list(ctx: typer.Context) -> None:
    """List the shows in your config with their perspective labels."""
    cfg: Config = ctx.obj.config()
    if not cfg.shows:
        typer.echo(f"No shows in {cfg.path}. Add one with `says feeds add`.")
        return
    for show in cfg.shows:
        label = show.perspective or "untagged"
        tags = f" [{', '.join(show.tags)}]" if show.tags else ""
        typer.echo(f"{show.name}  ({label}){tags}\n    {show.feed_url}")


@feeds_app.command("add")
def feeds_add(
    ctx: typer.Context,
    feed_url: Annotated[str, typer.Argument(help="RSS feed URL.")],
    name: Annotated[str, typer.Option(help="Display name for the show.")],
    perspective: Annotated[
        str | None, typer.Option(help="Your own label for this show, e.g. left/center/right.")
    ] = None,
    tag: Annotated[list[str] | None, typer.Option(help="Topic tag; repeatable.")] = None,
) -> None:
    """Append a show to your config file."""
    show = ShowConfig(name=name, feed_url=feed_url, perspective=perspective, tags=tuple(tag or ()))
    added = append_shows(ctx.obj.config_path, [show])
    if added:
        typer.echo(f"Added {name} to {ctx.obj.config_path}")
    else:
        typer.echo(f"{feed_url} is already in {ctx.obj.config_path}")


@feeds_app.command("import-opml")
def feeds_import_opml(
    ctx: typer.Context,
    opml: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="OPML file.")],
    perspective: Annotated[
        str | None, typer.Option(help="Apply one perspective label to every imported show.")
    ] = None,
) -> None:
    """Import feeds from an OPML export of your podcast app."""
    shows = parse_opml(opml.read_text(encoding="utf-8"), default_perspective=perspective)
    added = append_shows(ctx.obj.config_path, shows)
    typer.echo(f"Imported {len(added)} of {len(shows)} feeds into {ctx.obj.config_path}")
    if added and perspective is None:
        typer.echo("Imported shows are untagged; edit the config to add perspective labels.")


# --- ingest --------------------------------------------------------------


@app.command()
def ingest(
    ctx: typer.Context,
    show: Annotated[str | None, typer.Option(help="Only ingest the show with this name.")] = None,
    transcribe: Annotated[
        int,
        typer.Option(help="Transcribe up to N episodes per show that have no provided transcript."),
    ] = 0,
    transcriber: Annotated[
        str | None, typer.Option(help="Transcription backend (overrides settings.transcriber).")
    ] = None,
    keep_audio: Annotated[
        bool, typer.Option(help="Keep downloaded audio in the cache after transcription.")
    ] = False,
) -> None:
    """Fetch feeds, store new episodes, and index any available transcripts."""
    cfg: Config = ctx.obj.config()
    shows = [s for s in cfg.shows if show is None or s.name == show]
    if not shows:
        _fail(f"no matching shows in {cfg.path}")
    backend = None
    if transcribe > 0:
        try:
            backend = get_transcriber(transcriber or cfg.settings.transcriber)
        except (TranscriberUnavailable, ValueError) as exc:
            _fail(str(exc))
        if backend is None:
            _fail("--transcribe needs a backend; set settings.transcriber or pass --transcriber")
    exit_code = 0
    with ctx.obj.store(cfg) as store:
        for s in shows:
            report = ingest_show(
                store,
                s,
                transcriber=backend,
                audio_cache=cfg.settings.audio_cache,
                max_transcribe=transcribe,
                keep_audio=keep_audio,
            )
            typer.echo(report.summary())
            for err in report.errors:
                typer.echo(f"  {err}", err=True)
                exit_code = 2
    raise typer.Exit(exit_code)


@app.command()
def episodes(
    ctx: typer.Context,
    limit: Annotated[int, typer.Option(help="Maximum rows.")] = 50,
) -> None:
    """List stored episodes and whether each has a transcript."""
    with ctx.obj.store() as store:
        rows = store.list_episodes(limit)
    if not rows:
        typer.echo("No episodes yet. Run `says ingest`.")
    for r in rows:
        status = (
            f"{r['transcript_source']}, {r['segments']} segments"
            if r["transcript_source"]
            else "no transcript"
        )
        typer.echo(f"{r['id']:>5}  {r['show']} | {r['title']}  ({status})")


@transcript_app.command("import")
def transcript_import(
    ctx: typer.Context,
    episode_id: Annotated[int, typer.Argument(help="Episode id from `says episodes`.")],
    path: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    fmt: Annotated[str | None, typer.Option("--format", help="vtt, srt, or json.")] = None,
) -> None:
    """Attach a local VTT/SRT/JSON transcript file to an episode."""
    with ctx.obj.store() as store:
        try:
            count = import_transcript_file(store, episode_id, path, fmt)
        except (TranscriptError, ValueError) as exc:
            _fail(str(exc))
    typer.echo(f"Indexed {count} segments for episode {episode_id}")


# --- search and export ---------------------------------------------------


def _filters(
    perspective: list[str] | None, show: list[str] | None, speaker: str | None, since: str | None
) -> SearchFilters:
    return SearchFilters(
        perspectives=tuple(perspective or ()), shows=tuple(show or ()), speaker=speaker, since=since
    )


PerspectiveOpt = Annotated[
    list[str] | None,
    typer.Option("--perspective", "-p", help="Only shows with this label; repeatable."),
]
ShowOpt = Annotated[list[str] | None, typer.Option("--show", help="Only this show; repeatable.")]
SpeakerOpt = Annotated[str | None, typer.Option(help="Speaker name contains this text.")]
SinceOpt = Annotated[str | None, typer.Option(help="Published on or after (YYYY-MM-DD).")]
LimitOpt = Annotated[int, typer.Option(help="Maximum results.")]
RawOpt = Annotated[bool, typer.Option(help="Pass the query to SQLite FTS5 unchanged.")]


@app.command("search")
def search_cmd(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help='Words to find; use "quotes" for phrases.')],
    perspective: PerspectiveOpt = None,
    show: ShowOpt = None,
    speaker: SpeakerOpt = None,
    since: SinceOpt = None,
    limit: LimitOpt = 20,
    raw: RawOpt = False,
    by_perspective: Annotated[
        bool, typer.Option(help="Group results under each perspective label.")
    ] = False,
) -> None:
    """Find attributed quotes with show, episode, timestamp, and perspective label."""
    cfg: Config = ctx.obj.config()
    with ctx.obj.store(cfg) as store:
        try:
            hits = search(
                store,
                query,
                filters=_filters(perspective, show, speaker, since),
                limit=limit,
                raw=raw,
            )
        except ValueError as exc:
            _fail(str(exc))
        except sqlite3.OperationalError as exc:  # bad FTS5 syntax with --raw
            _fail(f"search failed: {exc}")
    if not hits:
        typer.echo("No results.")
        return
    groups = group_by_perspective(hits) if by_perspective else {"": hits}
    for label, group in groups.items():
        if label:
            typer.echo(f"== {label} ==")
        for hit in group:
            quote, _ = cap_quote(hit.quote, cfg.settings.quote_max_chars)
            who = hit.speaker or "unattributed"
            tag = hit.perspective or "untagged"
            typer.echo(
                f"[{format_timestamp(hit.start)}] {who} | {hit.show} ({tag}) | {hit.episode_title}"
            )
            typer.echo(f'    "{quote}"')
            if hit.timestamp_url:
                typer.echo(f"    {hit.timestamp_url}")


@app.command("export")
def export_cmd(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Search query, as for `says search`.")],
    fmt: Annotated[str, typer.Option("--format", "-f", help="markdown or json.")] = "markdown",
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write to file.")] = None,
    max_chars: Annotated[
        int | None, typer.Option(help="Quote length cap (default: settings.quote_max_chars).")
    ] = None,
    perspective: PerspectiveOpt = None,
    show: ShowOpt = None,
    speaker: SpeakerOpt = None,
    since: SinceOpt = None,
    limit: LimitOpt = 20,
    raw: RawOpt = False,
) -> None:
    """Export short cited quotes as Markdown or JSON."""
    exporter = EXPORTERS.get(fmt.lower())
    if exporter is None:
        _fail(f"unknown format {fmt!r}; use markdown or json")
    cfg: Config = ctx.obj.config()
    cap = max_chars or cfg.settings.quote_max_chars
    with ctx.obj.store(cfg) as store:
        try:
            hits = search(
                store,
                query,
                filters=_filters(perspective, show, speaker, since),
                limit=limit,
                raw=raw,
            )
        except ValueError as exc:
            _fail(str(exc))
        except sqlite3.OperationalError as exc:
            _fail(f"search failed: {exc}")
    text = exporter(hits, query, cap)
    if output:
        output.write_text(text, encoding="utf-8")
        typer.echo(f"Wrote {len(hits)} quotes to {output}")
    else:
        typer.echo(text, nl=False)


@app.command()
def stats(ctx: typer.Context) -> None:
    """Show counts of shows, episodes, transcripts, and indexed segments."""
    with ctx.obj.store() as store:
        for key, value in store.stats().items():
            typer.echo(f"{key:<12} {value}")


if __name__ == "__main__":
    app()
