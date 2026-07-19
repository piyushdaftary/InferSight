"""Basic smoke tests for the infersight package."""

from typer.testing import CliRunner

from infersight import __version__
from infersight.cli import app


def test_version_string() -> None:
    """__version__ is a non-empty string."""
    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_version_command() -> None:
    """infersight version prints the version string."""
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output
