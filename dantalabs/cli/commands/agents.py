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

@app.command("create-agent")
def create_agent_command(
    definition_id: Annotated[Optional[UUID], typer.Option(
        "--id", help="Agent Definition ID to use. If not provided, will prompt for selection."
    )] = None,
    name: Annotated[Optional[str], typer.Option(
        "--name", "-n", help="Name for the Agent. Required if not interactive."
    )] = None,
    description: Annotated[Optional[str], typer.Option(
        "--desc", "-d", help="Optional description for the Agent."
    )] = None,
    agent_type: Annotated[Optional[str], typer.Option(
        "--agent-type", "-t", help="Type of the agent (e.g., 'script', 'chat', 'tool')."
    )] = None,
    env_file: Annotated[Optional[Path], typer.Option(
        "--env-file", help="Path to a .env file containing environment variables as secrets."
    )] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Creates a new Maestro Agent from an existing Agent Definition."""
    from ..utils.client import get_client
    from ..utils.schemas import load_env_variables
    import dotenv
    
    client = get_client(org_id, url, token)
    
    # If no definition_id provided, list definitions and prompt for selection
    if not definition_id:
        try:
            typer.echo("Fetching available agent definitions...")
            definitions = client.list_agent_definitions()
            
            if not definitions:
                typer.secho("No agent definitions found. Create one first using 'dlm deploy'.", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            
            # Display definitions for selection
            typer.echo("\nAvailable agent definitions:")
            for i, definition in enumerate(definitions, 1):
                typer.echo(f"{i}) {definition.name} - {definition.description or 'No description'}")
            
            # Prompt for selection
            selection = typer.prompt("Select definition number", type=int)
            
            # Validate selection
            if selection < 1 or selection > len(definitions):
                typer.secho(f"Invalid selection. Please enter a number between 1 and {len(definitions)}.", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            
            # Get the selected definition
            selected_definition = definitions[selection - 1]
            definition_id = selected_definition.id
            typer.echo(f"Selected definition: {selected_definition.name} (ID: {definition_id})")
            
        except MaestroApiError as e:
            typer.secho(f"API Error listing definitions: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    # If name not provided, prompt for it
    agent_name = name
    if not agent_name:
        agent_name = typer.prompt("Enter agent name")
    
    # If agent_type not provided, prompt for it
    agent_type_value = agent_type
    if not agent_type_value:
        agent_type_value = typer.prompt("Enter agent type (e.g., script, chat, tool)", default="script")
    
    # Load secrets from .env file
    secrets = {}
    if not env_file:
        default_env_file = Path('.env')
        if default_env_file.exists():
            env_file = default_env_file
            typer.echo(f"Found default .env file in current directory.")
    
    if env_file and env_file.exists():
        try:
            typer.echo(f"Loading secrets from '{env_file}'...")
            secrets = dotenv.dotenv_values(env_file)
            if secrets:
                typer.echo(f"Loaded {len(secrets)} secrets.")
        except Exception as e:
            typer.secho(f"Error reading .env file '{env_file}': {e}", fg=typer.colors.YELLOW, err=True)
    
    # Create the agent
    try:
        from ...maestro.models import AgentCreate
        typer.echo(f"Creating agent '{agent_name}' with definition ID {definition_id}...")
        
        agent_payload = AgentCreate(
            name=agent_name,
            description=description,
            agent_type=agent_type_value,
            agent_definition_id=definition_id,
            secrets=secrets or None,
        )
        
        created_agent = client.create_agent(agent_payload)
        typer.secho(f"Agent '{created_agent.name}' created successfully (ID: {created_agent.id}).", fg=typer.colors.GREEN)
        
    except (MaestroValidationError, MaestroApiError) as e:
        typer.secho(f"API Error creating agent: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("update-agent")
def update_agent_command(
    agent_id: Annotated[Optional[UUID], typer.Argument(help="Agent ID to update")] = None,
    name: Annotated[Optional[str], typer.Option(
        "--name", "-n", help="New name for the Agent"
    )] = None,
    description: Annotated[Optional[str], typer.Option(
        "--desc", "-d", help="New description for the Agent"
    )] = None,
    agent_type: Annotated[Optional[str], typer.Option(
        "--agent-type", "-t", help="New type for the agent (e.g., 'script', 'chat', 'tool')"
    )] = None,
    definition_id: Annotated[Optional[UUID], typer.Option(
        "--definition-id", "--def", help="New Agent Definition ID to use"
    )] = None,
    env_file: Annotated[Optional[Path], typer.Option(
        "--env-file", help="Path to a .env file containing environment variables as secrets"
    )] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var)")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var)")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var)")] = None,
):
    """Updates an existing Maestro Agent with new properties."""
    from ..utils.client import get_client
    from ..config import load_config
    import dotenv
    
    client = get_client(org_id, url, token)
    
    # Resolve agent_id
    agent_id_to_use = None
    if agent_id:
        agent_id_to_use = agent_id
    elif client.agent_id:
        agent_id_to_use = client.agent_id
        config = load_config()
        agent_name_display = config.get("agent_name", "Default Agent")
        typer.echo(f"Using default agent: {agent_name_display} (ID: {agent_id_to_use})")
    else:
        typer.secho("Error: No agent ID provided or set. Use agent_id argument or 'dlm use-agent' first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    # Fetch current agent to show values being updated
    try:
        current_agent = client.get_agent(agent_id_to_use)
        typer.echo(f"Updating agent: {current_agent.name} (ID: {agent_id_to_use})")
    except MaestroApiError:
        typer.secho(f"Warning: Could not fetch current agent details.", fg=typer.colors.YELLOW, err=True)
        current_agent = None
    
    # Load secrets from .env file if provided
    secrets = None
    if not env_file:
        default_env_file = Path('.env')
        if default_env_file.exists():
            env_file = default_env_file
            typer.echo(f"Found default .env file in current directory.")
    
    if env_file and env_file.exists():
        try:
            typer.echo(f"Loading secrets from '{env_file}'...")
            secrets = dotenv.dotenv_values(env_file)
            if secrets:
                typer.echo(f"Loaded {len(secrets)} secrets.")
        except Exception as e:
            typer.secho(f"Error reading .env file '{env_file}': {e}", fg=typer.colors.YELLOW, err=True)
    
    # If no fields to update, exit
    if not (name or description or agent_type or definition_id or secrets):
        typer.secho("No fields to update. Provide at least one field to change.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)
    
    # Update the agent
    try:
        from ...maestro.models import AgentUpdate
        agent_update = AgentUpdate(
            name=name,
            description=description,
            agent_type=agent_type,
            agent_definition_id=definition_id,
            secrets=secrets
        )
        
        updated_agent = client.update_agent(agent_id_to_use, agent_update)
        typer.secho(f"Agent '{updated_agent.name}' updated successfully.", fg=typer.colors.GREEN)
        
    except (MaestroValidationError, MaestroApiError) as e:
        typer.secho(f"API Error updating agent: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("use-agent")
def use_agent_command(
    agent_id: Annotated[Optional[str], typer.Argument(help="Agent ID to use for this session")] = None,
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Optional agent name for reference")] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Set the default agent to use for subsequent commands."""
    from ..utils.client import get_client
    from ..config import load_config, save_config
    
    # Load config
    config = load_config()
    client = get_client(org_id, url, token)
    
    # If no agent_id provided, list agents and prompt for selection
    if not agent_id:
        try:
            typer.echo("Fetching available agents...")
            agents = client.list_agents()
            
            if not agents:
                typer.secho("No agents found. Create one first using 'dlm create-agent'.", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            
            # Display agents for selection
            typer.echo("\nAvailable agents:")
            for i, agent in enumerate(agents, 1):
                typer.echo(f"{i}) {agent.name} - {agent.description or 'No description'} (ID: {agent.id})")
            
            # Prompt for selection
            selection = typer.prompt("Select agent number", type=int)
            
            # Validate selection
            if selection < 1 or selection > len(agents):
                typer.secho(f"Invalid selection. Please enter a number between 1 and {len(agents)}.", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            
            # Get the selected agent
            selected_agent = agents[selection - 1]
            agent_id_uuid = selected_agent.id
            agent_name = selected_agent.name
            typer.echo(f"Selected agent: {agent_name} (ID: {agent_id_uuid})")
            
        except MaestroApiError as e:
            typer.secho(f"API Error listing agents: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    else:
        # Validate agent_id is a valid UUID
        try:
            agent_id_uuid = UUID(agent_id)
        except ValueError:
            typer.secho(f"Error: '{agent_id}' is not a valid agent ID (should be a UUID).", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        
        # Optionally verify the agent exists
        try:
            agent = client.get_agent(agent_id_uuid)
            agent_name = agent.name
            typer.echo(f"Found agent: {agent_name} (ID: {agent_id_uuid})")
        except MaestroApiError as e:
            typer.secho(f"Warning: Could not verify agent existence: {e}", fg=typer.colors.YELLOW, err=True)
            agent_name = name or "Unknown"
    
    # Update configuration
    config["agent_id"] = str(agent_id_uuid)
    if name or agent_name:
        config["agent_name"] = name or agent_name
    
    # Save configuration
    save_config(config)
    
    typer.secho(f"Default agent set to: {agent_name} (ID: {agent_id_uuid})", fg=typer.colors.GREEN)
    typer.echo("This agent will be used for future commands unless overridden.")

@app.command("run-agent")
def run_agent_command(
    input_json: Annotated[Optional[str], typer.Argument(help="JSON string of input variables or path to JSON file")] = None,
    agent_id: Annotated[Optional[str], typer.Option("--agent-id", "-a", help="Agent ID to run (overrides default agent)")] = None,
    input_file: Annotated[Optional[Path], typer.Option("--file", "-f", help="Path to JSON file containing input variables")] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Run an agent synchronously with provided input variables."""
    from ..utils.client import get_client
    from ..config import load_config
    import json
    
    # Handle input variables
    input_variables = {}
    
    # First check if input_file is provided
    if input_file:
        if not input_file.exists():
            typer.secho(f"Error: Input file '{input_file}' does not exist.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        try:
            with open(input_file, 'r') as f:
                input_variables = json.load(f)
            typer.echo(f"Loaded input variables from file: {input_file}")
        except json.JSONDecodeError as e:
            typer.secho(f"Error: Could not parse JSON from file '{input_file}': {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    # Then check if input_json is provided
    elif input_json:
        # Check if input_json is a file path
        potential_file = Path(input_json)
        if potential_file.exists() and potential_file.is_file():
            try:
                with open(potential_file, 'r') as f:
                    input_variables = json.load(f)
                typer.echo(f"Loaded input variables from file: {potential_file}")
            except json.JSONDecodeError as e:
                typer.secho(f"Error: Could not parse JSON from file '{potential_file}': {e}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
        else:
            # Try to parse as JSON string
            try:
                input_variables = json.loads(input_json)
                typer.echo("Parsed input variables from JSON string")
            except json.JSONDecodeError as e:
                typer.secho(f"Error: Could not parse JSON string: {e}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
    
    # If no input was provided, use empty dict
    if not input_variables:
        typer.echo("No input variables provided, using empty dictionary")
        input_variables = {}
    
    # Get client and resolve agent_id
    client = get_client(org_id, url, token)
    
    agent_id_to_use = None
    if agent_id:
        try:
            agent_id_to_use = UUID(agent_id)
        except ValueError:
            typer.secho(f"Error: '{agent_id}' is not a valid agent ID (should be a UUID).", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    elif client.agent_id:
        agent_id_to_use = client.agent_id
        config = load_config()
        agent_name = config.get("agent_name", "Default Agent")
        typer.echo(f"Using default agent: {agent_name} (ID: {agent_id_to_use})")
    else:
        typer.secho("Error: No agent ID provided or set. Use --agent-id or 'dlm use-agent' first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    # Execute the agent code
    try:
        typer.echo(f"Running agent {agent_id_to_use} with sync execution...")
        execution = client.execute_agent_code_sync(
            variables=input_variables,
            agent_id=agent_id_to_use
        )
        
        # Display results
        typer.secho("Execution completed successfully!", fg=typer.colors.GREEN)
        return execution
        
    except MaestroApiError as e:
        typer.secho(f"API Error executing agent: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)