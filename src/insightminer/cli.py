"""Command-line entry point: automation, containers, tests, and break-glass recovery.

Every command is a thin wrapper over a service function the web UI also calls.
"""

from __future__ import annotations

import typer

from insightminer import __version__

app = typer.Typer(no_args_is_help=True, add_completion=False, help="Insight Miner CLI")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"insightminer {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Print the version."
    ),
) -> None:
    """Insight Miner command-line interface."""


if __name__ == "__main__":  # pragma: no cover
    app()
