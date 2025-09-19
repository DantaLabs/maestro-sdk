import typer
from typing import Annotated

from ..config import load_config, save_config


def set_url_command(
    url: Annotated[str, typer.Argument(help="Maestro API Base URL, e.g., https://dantalabs.com")],
):
    """Set the Maestro API base URL used by the CLI."""
    normalized_url = url.strip().rstrip("/")

    if not (normalized_url.startswith("http://") or normalized_url.startswith("https://")):
        typer.secho(
            "Error: URL must start with http:// or https://",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)

    config = load_config()
    previous_url = config.get("base_url")
    config["base_url"] = normalized_url
    save_config(config)

    if previous_url and previous_url != normalized_url:
        typer.secho("Updated base URL.", fg=typer.colors.GREEN)
        typer.echo(f"  From: {previous_url}")
        typer.echo(f"    To: {normalized_url}")
    else:
        typer.secho("Base URL set.", fg=typer.colors.GREEN)
        typer.echo(f"  URL: {normalized_url}")


