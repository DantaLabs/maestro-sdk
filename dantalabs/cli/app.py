import typer
from .commands import setup, deploy, agents, bundles, status
from .config import VERSION

# --- Typer App ---
app = typer.Typer(
    name="dlm",
    help="DantaLabs Maestro CLI - Interact with the Maestro service.",
    add_completion=False,
)

# Add individual commands directly to the app
app.command()(setup.setup_command)
app.command("deploy")(deploy.deploy_command)
app.command("list-agents")(agents.list_agents_cmd)
app.command("list-definitions")(agents.list_definitions_cmd)
app.command("status")(status.status_command)

@app.command()
def version():
    """Show version information."""
    typer.echo(VERSION)

if __name__ == "__main__":
    app()