"""InferSight command-line interface."""
import typer

app = typer.Typer(
    name="infersight",
    help="The open-source intelligence layer for AI inference infrastructure.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the InferSight version."""
    from infersight import __version__
    typer.echo(f"infersight {__version__}")


if __name__ == "__main__":
    app()
