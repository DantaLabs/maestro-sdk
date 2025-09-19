import typer
from typing import Optional, Annotated
from uuid import UUID
from ..config import load_config, load_project_state
from ..utils.client import get_client
from ...maestro.exceptions import MaestroApiError

app = typer.Typer()

@app.command()
def status_command(
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Show status of the current project and connected agents."""
    client = get_client(org_id, url, token)
    
    typer.echo("🤖 DantaLabs Maestro CLI Status")
    typer.echo("=" * 40)
    
    # Show current configuration
    config = load_config()
    typer.echo(f"📍 API URL: {config.get('base_url', 'Not configured')}")
    typer.echo(f"🏢 Organization ID: {config.get('organization_id', 'Not configured')}")
    
    # Show project state
    project_state = load_project_state()
    if project_state:
        typer.echo("\n📁 Current Project:")
        typer.echo(f"  Agent Name: {project_state.get('agent_name', 'N/A')}")
        typer.echo(f"  Definition ID: {project_state.get('agent_definition_id', 'N/A')}")
        typer.echo(f"  Agent ID: {project_state.get('agent_id', 'N/A')}")
        typer.echo(f"  Last Deploy Mode: {project_state.get('last_deploy_mode', 'N/A')}")
        if project_state.get('last_deployed_at'):
            typer.echo(f"  Last Deployed: {project_state['last_deployed_at']}")
        
        # Try to fetch current status of the agent
        definition_id = project_state.get('agent_definition_id')
        agent_id = project_state.get('agent_id')
        
        if definition_id:
            try:
                definition = client.get_agent_definition(UUID(definition_id))
                typer.echo(f"  ✅ Definition exists: {definition.name}")
            except:
                typer.echo(f"  ❌ Definition not found (may have been deleted)")
        
        if agent_id:
            try:
                agent = client.get_agent(UUID(agent_id))
                typer.echo(f"  ✅ Agent exists: {agent.name} ({agent.agent_type})")
            except:
                typer.echo(f"  ❌ Agent not found (may have been deleted)")
    else:
        typer.echo("\n📁 No project state found in current directory")
        typer.echo("   Run 'dlm deploy' to deploy an agent from this directory")
    
    # Show API connectivity
    typer.echo("\n🌐 API Connectivity:")
    try:
        if client.health_check():
            typer.secho("  ✅ API is reachable and healthy", fg=typer.colors.GREEN)
        else:
            typer.secho("  ❌ API health check failed", fg=typer.colors.RED)
    except:
        typer.secho("  ❌ Cannot reach API", fg=typer.colors.RED)