import typer
from typing import Optional, Annotated
from uuid import UUID
from pathlib import Path
from ..utils.client import get_client
from ..config import load_config, save_config
from ...maestro.models import AgentCreate, AgentUpdate
from ...maestro.exceptions import MaestroApiError, MaestroValidationError

app = typer.Typer()

@app.command("list-agents")  
def list_agents_cmd(
    show_definition: Annotated[bool, typer.Option(
        "--show-def", 
        help="Show agent definition information"
    )] = False,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """List all agents in the current organization."""
    client = get_client(org_id, url, token)
    
    try:
        agents = client.list_agents()
        
        if not agents:
            typer.echo("No agents found.")
            return
        
        typer.echo(f"Found {len(agents)} agent(s):")
        typer.echo()
        
        for agent in agents:
            typer.echo(f"• {agent.name} (ID: {agent.id})")
            if agent.description:
                typer.echo(f"  Description: {agent.description}")
            typer.echo(f"  Type: {agent.agent_type}")
            typer.echo(f"  Created: {agent.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            
            if show_definition and agent.agent_definition_id:
                try:
                    definition = client.get_agent_definition(agent.agent_definition_id)
                    typer.echo(f"  Definition: {definition.name} (ID: {agent.agent_definition_id})")
                except:
                    typer.echo(f"  Definition ID: {agent.agent_definition_id}")
            
            typer.echo()
    
    except MaestroApiError as e:
        typer.secho(f"API Error listing agents: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("list-definitions")
def list_definitions_cmd(
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """List all agent definitions in the current organization."""
    client = get_client(org_id, url, token)
    
    try:
        definitions = client.list_agent_definitions()
        
        if not definitions:
            typer.echo("No agent definitions found.")
            return
        
        typer.echo(f"Found {len(definitions)} definition(s):")
        typer.echo()
        
        for definition in definitions:
            typer.echo(f"• {definition.name} (ID: {definition.id})")
            if definition.description:
                typer.echo(f"  Description: {definition.description}")
            typer.echo(f"  Type: {definition.definition_type or 'python'}")
            typer.echo(f"  Created: {definition.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
            typer.echo()
    
    except MaestroApiError as e:
        typer.secho(f"API Error listing definitions: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

# Placeholder functions for other commands - will need full implementation
def create_agent_command():
    """Create agent command - placeholder."""
    pass

def update_agent_command():
    """Update agent command - placeholder."""
    pass

def use_agent_command():
    """Use agent command - placeholder."""
    pass

def run_agent_command():
    """Run agent command - placeholder."""
    pass