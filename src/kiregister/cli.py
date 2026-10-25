"""Command line: bootstrap, apply, seed, verify."""

from __future__ import annotations

import logging
import sys
from typing import Annotated

import typer

from . import metadata
from .auth import AzCliTokens, ClientCredentialTokens
from .client import DataverseClient
from .config import load_settings
from .definitions import load_definitions

app = typer.Typer(help="Nordstern KI-Register: Dataverse-Provisionierung als Code.", no_args_is_help=True)
EnvOpt = Annotated[str, typer.Option("--env", help="Umgebung aus config.toml: dev oder test")]
ONLY_CHOICES = ("metadata", "security", "app")


@app.callback()
def main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _client(env: str) -> tuple[DataverseClient, object, object]:
    settings = load_settings(env)
    defs = load_definitions(settings.definitions_dir)
    return DataverseClient(settings.api, ClientCredentialTokens(settings), solution=settings.solution), settings, defs


@app.command()
def bootstrap(env: EnvOpt = "dev") -> None:
    """Anwendungsbenutzer fuer den Service Principal anlegen (benoetigt `az login` des Eigentuemers)."""
    from .bootstrap import ensure_application_user
    settings = load_settings(env)
    if not settings.url or not settings.client_id:
        raise typer.BadParameter("CLIENT_ID und die Umgebungs-URL muessen gesetzt sein (.env, `uv run --env-file .env ...`)")
    client = DataverseClient(settings.api, AzCliTokens(settings.url))
    typer.echo(f"anwendungsbenutzer: {ensure_application_user(client, settings.client_id)}")


@app.command()
def apply(env: EnvOpt = "dev", only: Annotated[str | None, typer.Option("--only", help="metadata | security | app")] = None) -> None:
    """Metadaten, Sicherheit und App anlegen oder aktualisieren (idempotent)."""
    if only is not None and only not in ONLY_CHOICES:
        raise typer.BadParameter(f"--only muss einer von {', '.join(ONLY_CHOICES)} sein", param_hint="--only")
    client, settings, defs = _client(env)
    if only in (None, "metadata"):
        typer.echo(f"metadaten: {metadata.apply_metadata(client, settings, defs)}")
    if only in (None, "security"):
        from .security import apply_security
        typer.echo(f"sicherheit: {apply_security(client, settings, defs)}")
    if only in (None, "app"):
        from .app import apply_app
        typer.echo(f"app: {apply_app(client, settings, defs)}")


@app.command()
def seed(env: EnvOpt = "dev") -> None:
    """Fiktive Registerdaten laden (upsert mit festen GUIDs)."""
    from .seed import load_seed
    client, settings, defs = _client(env)
    typer.echo(f"seed: {load_seed(client, settings, defs)}")


@app.command()
def verify(env: EnvOpt = "dev") -> None:
    """Pruefen, ob Metadaten, Sicherheit, App und Seed dem Soll entsprechen; Exit-Code 1 bei Abweichung."""
    from .verify import run_verify
    client, settings, defs = _client(env)
    failures = run_verify(client, settings, defs)
    for f in failures:
        typer.echo(f"FEHLT: {f}")
    typer.echo("verify: ok" if not failures else f"verify: {len(failures)} Abweichungen")
    if failures:
        raise typer.Exit(code=1)
