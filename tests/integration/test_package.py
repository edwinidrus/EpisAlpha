"""Package and console-entry smoke tests."""

from importlib.metadata import version

from typer.testing import CliRunner

import episalpha
from episalpha.cli import app


def test_package_version_matches_installed_metadata() -> None:
    assert episalpha.__version__ == version("episalpha")


def test_console_entry_prints_version() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout == f"{episalpha.__version__}\n"
