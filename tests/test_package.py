"""Basic smoke tests for the infersight package."""

from typer.testing import CliRunner

from infersight import __version__
from infersight.cli import app


def test_version_string() -> None:
    """__version__ is a non-empty string."""
    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_version_command() -> None:
    """infersight version command prints the version string."""
    runner = CliRunner()
    # Single-command Typer app — invoke with no subcommand name
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert __version__ in result.output
