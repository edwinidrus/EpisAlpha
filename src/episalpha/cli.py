"""Command-line entry point for EpisAlpha."""

from typing import Annotated

import typer

from episalpha import __version__

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    invoke_without_command=True,
    help="Evidence-grounded personal investment research workbench.",
)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", help="Print the installed EpisAlpha version."),
    ] = False,
) -> None:
    """Configure top-level CLI options."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()
