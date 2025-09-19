import typer
from .commands import setup, deploy, agents, bundles, status, templates, services, agentdb, settings
from .config import VERSION

# --- Typer App ---
app = typer.Typer(
    name="dlm",
    help="DantaLabs Maestro CLI - Interact with the Maestro service.",
    add_completion=False,
)

# Add individual commands directly to the app (using correct function names)
app.command("setup")(setup.setup_command)
app.command("deploy")(deploy.deploy_command)
app.command("list-agents")(agents.list_agents_cmd)
app.command("list-definitions")(agents.list_definitions_cmd)
app.command("status")(status.status_command)
app.command("create-agent")(agents.create_agent_command)
app.command("update-agent")(agents.update_agent_command)
app.command("use-agent")(agents.use_agent_command)
app.command("run-agent")(agents.run_agent_command)
app.command("create-bundle")(bundles.create_bundle_command)
app.command("upload-bundle")(bundles.upload_bundle_command)
app.command("deploy-bundle")(bundles.deploy_bundle_command)
app.command("update-bundle")(bundles.update_bundle_command)
app.command("download-definition-bundle")(bundles.download_definition_bundle_command)
app.command("init")(templates.init_command)
app.command("list-templates")(templates.list_templates_command)
app.command("set-url")(settings.set_url_command)

# Add service commands as a sub-app
app.add_typer(services.app, name="service", help="Manage agent services")

# Add agentdb commands as a sub-app
app.add_typer(agentdb.app, name="agentdb", help="Manage agent databases and connections")

@app.command()
def version():
    """Show version information."""
    typer.echo(VERSION)

if __name__ == "__main__":
    app()