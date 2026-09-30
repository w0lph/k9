"""Command-line entry point: ``cac``."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from .config import QUERIES, DataPaths
from .europepmc import EuropePMCClient
from .pipeline import (
    build_manifest,
    convert_fulltext,
    fetch_fulltext,
    fetch_fulltext_ncbi,
    fetch_metadata,
    rebuild_records,
)

app = typer.Typer(help="Build the canine aging literature corpus from Europe PMC.", no_args_is_help=True)


def _paths(data_dir: Path) -> DataPaths:
    return DataPaths(root=data_dir)


def _client_factory(max_attempts: int):
    def make():
        return EuropePMCClient(max_attempts=max_attempts)

    return make


@app.callback()
def _setup(verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging.")):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


@app.command("queries")
def show_queries():
    """Print the configured Europe PMC queries."""
    for tier, q in QUERIES.items():
        typer.echo(f"[{tier}]\n{q}\n")


@app.command("fetch-metadata")
def cmd_fetch_metadata(
    data_dir: Path = typer.Option(Path("data"), help="Output directory."),
    tier: list[str] = typer.Option(None, help="Tier(s) to fetch; default all."),
    page_size: int = typer.Option(200, help="Europe PMC page size (max 1000)."),
    max_attempts: int = typer.Option(10, help="Retries per request on 429/5xx/transport errors."),
):
    """Run the search queries and write records.jsonl (persisted after every tier)."""
    with _client_factory(max_attempts)() as client:
        stats = fetch_metadata(_paths(data_dir), tiers=tier or None, page_size=page_size, client=client)
    for s in stats:
        typer.echo(f"{s.tier}: hitCount={s.hit_count} fetched={s.fetched} pages={s.pages}")


@app.command("rebuild-records")
def cmd_rebuild_records(data_dir: Path = typer.Option(Path("data"))):
    """Rebuild records.jsonl from the raw search pages already on disk (no network)."""
    typer.echo(json.dumps(rebuild_records(_paths(data_dir)), indent=2))


@app.command("fetch-fulltext")
def cmd_fetch_fulltext(
    data_dir: Path = typer.Option(Path("data")),
    force: bool = typer.Option(False, help="Re-download files already on disk."),
    workers: int = typer.Option(4, help="Parallel downloads."),
    limit: int = typer.Option(None, help="Only try the first N candidates (smoke test)."),
    max_attempts: int = typer.Option(3, help="Retries per request; keep small, re-run the step instead."),
    breaker: int = typer.Option(12, help="Abort after this many consecutive failures (service down)."),
    source: str = typer.Option("europepmc", help="europepmc (per-file) or ncbi (batched E-utilities)."),
):
    """Download JATS XML for every record with a PMCID (idempotent; re-run until remaining=0)."""
    if source == "ncbi":
        typer.echo(json.dumps(fetch_fulltext_ncbi(_paths(data_dir), limit=limit, force=force), indent=2))
        return
    result = fetch_fulltext(
        _paths(data_dir),
        force=force,
        workers=workers,
        limit=limit,
        client_factory=_client_factory(max_attempts),
        breaker_threshold=breaker,
    )
    typer.echo(json.dumps(result, indent=2))
    if result["aborted"]:
        raise typer.Exit(3)


@app.command("convert")
def cmd_convert(
    data_dir: Path = typer.Option(Path("data")),
    force: bool = typer.Option(False),
):
    """Convert downloaded JATS XML to Markdown."""
    typer.echo(json.dumps(convert_fulltext(_paths(data_dir), force=force), indent=2))


@app.command("manifest")
def cmd_manifest(data_dir: Path = typer.Option(Path("data"))):
    """Build manifest.parquet/csv and corpus_version.json."""
    typer.echo(json.dumps(build_manifest(_paths(data_dir))["counts"], indent=2))


@app.command("run")
def cmd_run(
    data_dir: Path = typer.Option(Path("data")),
    workers: int = typer.Option(4),
    page_size: int = typer.Option(200),
    max_attempts: int = typer.Option(10),
):
    """All steps: fetch-metadata, fetch-fulltext, convert, manifest."""
    paths = _paths(data_dir)
    with _client_factory(max_attempts)() as client:
        for s in fetch_metadata(paths, page_size=page_size, client=client):
            typer.echo(f"{s.tier}: hitCount={s.hit_count} fetched={s.fetched} pages={s.pages}")
    typer.echo(json.dumps(fetch_fulltext(paths, workers=workers, client_factory=_client_factory(3))))
    typer.echo(json.dumps(convert_fulltext(paths)))
    typer.echo(json.dumps(build_manifest(paths)["counts"], indent=2))


@app.command("stats")
def cmd_stats(data_dir: Path = typer.Option(Path("data"))):
    """Print corpus_version.json counts."""
    vf = _paths(data_dir).version_file
    if not vf.exists():
        typer.echo("no corpus_version.json yet; run `cac manifest`.")
        raise typer.Exit(1)
    typer.echo(json.dumps(json.loads(vf.read_text(encoding="utf-8"))["counts"], indent=2))
