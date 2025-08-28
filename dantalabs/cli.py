import typer
import os
import sys
import json 
from pathlib import Path
from typing import Optional, Annotated, Dict, Any, Tuple
from uuid import UUID
import dotenv

from .maestro import MaestroClient
from .maestro.models import AgentDefinitionCreate, AgentCreate, AgentUpdate, Agent, AgentDefinition
from .maestro.exceptions import MaestroApiError, MaestroAuthError, MaestroValidationError
from datetime import datetime
import os

# --- Configuration File Handling ---
CONFIG_DIR = Path.home() / ".maestro"
CONFIG_FILE = CONFIG_DIR / "config.json"
PROJECT_STATE_FILE = ".maestro_state.json"
VERSION = "0.0.1"

def load_config() -> Dict[str, Any]:
    """Loads configuration from the JSON file."""
    if CONFIG_FILE.is_file():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            typer.secho(f"Warning: Could not decode configuration file at {CONFIG_FILE}. Ignoring.", fg=typer.colors.YELLOW, err=True)
        except Exception as e:
            typer.secho(f"Warning: Could not read configuration file at {CONFIG_FILE}: {e}. Ignoring.", fg=typer.colors.YELLOW, err=True)
    return {}

def save_config(config_data: Dict[str, Any]):
    """Saves configuration to the JSON file."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True) 
        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f, indent=4)
    except Exception as e:
        typer.secho(f"Error: Could not write configuration file at {CONFIG_FILE}: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

def load_project_state(project_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Loads project-specific state from the local .maestro_state.json file."""
    if project_dir is None:
        project_dir = Path.cwd()
    
    state_file = project_dir / PROJECT_STATE_FILE
    if state_file.exists():
        try:
            with open(state_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            typer.secho(f"Warning: Could not decode project state file at {state_file}. Ignoring.", fg=typer.colors.YELLOW, err=True)
        except Exception as e:
            typer.secho(f"Warning: Could not read project state file at {state_file}: {e}. Ignoring.", fg=typer.colors.YELLOW, err=True)
    return {}

def save_project_state(state_data: Dict[str, Any], project_dir: Optional[Path] = None):
    """Saves project-specific state to the local .maestro_state.json file."""
    if project_dir is None:
        project_dir = Path.cwd()
    
    state_file = project_dir / PROJECT_STATE_FILE
    try:
        with open(state_file, "w") as f:
            json.dump(state_data, f, indent=4)
    except Exception as e:
        typer.secho(f"Error: Could not write project state file at {state_file}: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

def get_deploy_mode(client: "MaestroClient", agent_name: str, project_dir: Optional[Path] = None) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Determines the deployment mode: 'create', 'update', or 'redeploy'.
    
    Returns:
        Tuple of (mode, existing_data) where mode is 'create', 'update', or 'redeploy'
        and existing_data contains info about existing definition/agent if found.
    """
    state = load_project_state(project_dir)
    existing_data = {}
    
    # Check if we have stored agent/definition info from previous deployments
    stored_definition_id = state.get("agent_definition_id")
    stored_agent_id = state.get("agent_id")
    stored_agent_name = state.get("agent_name")
    
    # If we have stored IDs and the name matches, try to fetch existing resources
    if stored_definition_id and stored_agent_name == agent_name:
        try:
            # Check if definition still exists
            definition = client.get_agent_definition(UUID(stored_definition_id))
            existing_data["definition"] = definition
            
            # Check if agent still exists
            if stored_agent_id:
                try:
                    agent = client.get_agent(UUID(stored_agent_id))
                    existing_data["agent"] = agent
                    return "update", existing_data
                except MaestroApiError:
                    # Agent was deleted but definition exists
                    return "redeploy", existing_data
            else:
                # No agent stored, definition exists
                return "redeploy", existing_data
                
        except MaestroApiError:
            # Definition was deleted, start fresh
            pass
    
    # Fallback: search by name in case state file is missing/outdated
    try:
        all_definitions = client.list_agent_definitions(name=agent_name)
        if all_definitions:
            definition = all_definitions[0]  # Take first match
            existing_data["definition"] = definition
            
            # Check for agents using this definition
            all_agents = client.list_agents(name=agent_name)
            if all_agents:
                agent = all_agents[0]  # Take first match
                existing_data["agent"] = agent
                return "update", existing_data
            else:
                return "redeploy", existing_data
    except MaestroApiError:
        pass
    
    return "create", existing_data

def load_schemas(file_path: Path, schema_file: Optional[Path] = None) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Loads input, output, and memory schemas from JSON file."""
    input_schema = {}
    output_schema = {}
    memory_template = {}
    
    # Try to load schemas from JSON file with same name if no specific file is provided
    if not schema_file:
        if file_path.is_file():
            default_schema_file = file_path.with_suffix('.json')
        else:
            default_schema_file = file_path / f"{file_path.name}.json"
        
        if default_schema_file.exists():
            schema_file = default_schema_file
    
    # Load schemas from the JSON file if it exists
    if schema_file and schema_file.exists():
        try:
            typer.echo(f"Loading schemas from '{schema_file}'...")
            with open(schema_file, 'r') as f:
                schema_data = json.load(f)
                
            # Extract schemas from the file
            if 'input' in schema_data:
                input_schema = schema_data['input']
                typer.echo("Input schema loaded.")
            
            if 'output' in schema_data:
                output_schema = schema_data['output']
                typer.echo("Output schema loaded.")
            
            if 'memory' in schema_data:
                memory_template = schema_data['memory']
                typer.echo("Memory template loaded.")
        except json.JSONDecodeError as e:
            typer.secho(f"Error parsing JSON file '{schema_file}': {e}", fg=typer.colors.RED, err=True)
            typer.secho("Continuing with default empty schemas.", fg=typer.colors.YELLOW)
        except Exception as e:
            typer.secho(f"Error reading schema file '{schema_file}': {e}", fg=typer.colors.RED, err=True)
            typer.secho("Continuing with default empty schemas.", fg=typer.colors.YELLOW)
    
    return input_schema, output_schema, memory_template

def load_env_variables(base_dir: Path, env_file: Optional[Path] = None) -> Dict[str, Any]:
    """Loads environment variables from .env file."""
    env_variables = {}
    
    # Try to load environment variables from .env file
    if not env_file:
        default_env_file = base_dir / '.env'
        if default_env_file.exists():
            env_file = default_env_file
    
    if env_file and env_file.exists():
        try:
            typer.echo(f"Loading environment variables from '{env_file}'...")
            env_variables = dotenv.dotenv_values(env_file)
            if env_variables:
                typer.echo(f"Loaded {len(env_variables)} environment variables.")
            else:
                typer.echo("No environment variables found in .env file.")
        except Exception as e:
            typer.secho(f"Error reading .env file '{env_file}': {e}", fg=typer.colors.RED, err=True)
            typer.secho("Continuing without environment variables.", fg=typer.colors.YELLOW)
    
    return env_variables

def deploy_single_file(
    client: "MaestroClient",
    agent_code: str,
    agent_name: str,
    description: Optional[str],
    agent_type: str,
    deploy_mode: str,
    existing_data: Dict[str, Any],
    create_agent: bool,
    input_schema: Dict[str, Any],
    output_schema: Dict[str, Any],
    memory_template: Dict[str, Any],
    env_variables: Dict[str, Any]
) -> Tuple[Optional[UUID], Optional[UUID]]:
    """Deploys a single Python file as an agent definition and optionally an agent."""
    definition_id = None
    agent_id = None
    
    # Handle definition
    if deploy_mode == "create":
        typer.echo("Creating new Agent Definition...")
        definition_payload = AgentDefinitionCreate(
            name=agent_name,
            description=description,
            definition=agent_code,
            definition_type='python',
            input_schema=input_schema,
            output_schema=output_schema,
            memory_template=memory_template,
            environment_variables=env_variables,
        )
        created_def = client.create_agent_definition(definition_payload)
        definition_id = created_def.id
        typer.secho(f"Agent Definition '{created_def.name}' created (ID: {definition_id}).", fg=typer.colors.GREEN)
    
    elif deploy_mode == "update":
        existing_definition = existing_data["definition"]
        definition_id = existing_definition.id
        typer.echo(f"Updating existing Agent Definition (ID: {definition_id})...")
        definition_payload = AgentDefinitionCreate(
            name=agent_name,
            description=description or existing_definition.description,
            definition=agent_code,
            definition_type='python',
            input_schema=input_schema or existing_definition.input_schema,
            output_schema=output_schema or existing_definition.output_schema,
            memory_template=memory_template or existing_definition.memory_template,
            environment_variables=env_variables or existing_definition.environment_variables,
        )
        updated_def = client.update_agent_definition(definition_id, definition_payload)
        typer.secho(f"Agent Definition '{updated_def.name}' updated (ID: {updated_def.id}).", fg=typer.colors.GREEN)
    
    elif deploy_mode == "redeploy":
        existing_definition = existing_data["definition"]
        definition_id = existing_definition.id
        typer.echo(f"Redeploying with existing Agent Definition (ID: {definition_id})...")
        # Update the definition with new code
        definition_payload = AgentDefinitionCreate(
            name=agent_name,
            description=description or existing_definition.description,
            definition=agent_code,
            definition_type='python',
            input_schema=input_schema or existing_definition.input_schema,
            output_schema=output_schema or existing_definition.output_schema,
            memory_template=memory_template or existing_definition.memory_template,
            environment_variables=env_variables or existing_definition.environment_variables,
        )
        updated_def = client.update_agent_definition(definition_id, definition_payload)
        typer.secho(f"Agent Definition '{updated_def.name}' redeployed (ID: {updated_def.id}).", fg=typer.colors.GREEN)
    
    # Handle agent creation/update
    if create_agent and definition_id:
        if deploy_mode == "update" and "agent" in existing_data:
            existing_agent = existing_data["agent"]
            agent_id = existing_agent.id
            typer.echo(f"Updating existing Agent (ID: {agent_id})...")
            agent_update_data = AgentUpdate(
                name=agent_name,
                description=description or existing_agent.description,
                agent_definition_id=definition_id,
                agent_type=agent_type,
                capabilities=existing_agent.capabilities,
                agent_metadata=existing_agent.agent_metadata
            )
            updated_agent = client.update_agent(agent_id, agent_update_data)
            typer.secho(f"Agent '{updated_agent.name}' updated (ID: {updated_agent.id}).", fg=typer.colors.GREEN)
        else:
            typer.echo(f"Creating new Agent linked to definition {definition_id}...")
            agent_payload = AgentCreate(
                name=agent_name,
                description=description,
                agent_type=agent_type,
                agent_definition_id=definition_id,
            )
            created_agent = client.create_agent(agent_payload)
            agent_id = created_agent.id
            typer.secho(f"Agent '{created_agent.name}' created (ID: {agent_id}).", fg=typer.colors.GREEN)
    
    return definition_id, agent_id

def deploy_bundle_with_state(
    client: "MaestroClient",
    source_dir: Path,
    agent_name: str,
    description: Optional[str],
    agent_type: str,
    deploy_mode: str,
    existing_data: Dict[str, Any],
    create_agent: bool,
    schema_file: Optional[Path],
    env_file: Optional[Path],
    project_dir: Path
) -> None:
    """Deploys a directory as a bundle with state tracking."""
    # Load schemas and environment variables for bundle
    input_schema, output_schema, memory_template = load_schemas(source_dir, schema_file)
    env_variables = load_env_variables(source_dir, env_file)
    
    definition_id = None
    agent_id = None
    
    if deploy_mode == "create":
        # Create new bundle
        typer.echo("Creating and deploying new bundle...")
        agent_definition = client.create_and_upload_bundle(
            source_dir=str(source_dir),
            name=agent_name,
            description=description,
            input_schema=input_schema if input_schema else None,
            output_schema=output_schema if output_schema else None,
            shareable=False
        )
        definition_id = agent_definition.id
        typer.secho(f"Agent Definition '{agent_definition.name}' created (ID: {definition_id}).", fg=typer.colors.GREEN)
    
    elif deploy_mode in ["update", "redeploy"]:
        existing_definition = existing_data["definition"]
        definition_id = existing_definition.id
        
        # Create new bundle and update existing definition
        typer.echo(f"Updating existing bundle definition (ID: {definition_id})...")
        bundle_path = client.create_bundle(
            source_dir=str(source_dir),
            include_requirements=True,
            install_dependencies=True
        )
        
        try:
            updated_definition = client.update_agent_bundle(
                definition_id=definition_id,
                bundle_path=bundle_path
            )
            typer.secho(f"Agent Definition '{updated_definition.name}' updated (ID: {updated_definition.id}).", fg=typer.colors.GREEN)
        finally:
            # Clean up temporary bundle
            try:
                os.remove(bundle_path)
            except:
                pass
    
    # Handle agent creation/update
    if create_agent and definition_id:
        if deploy_mode == "update" and "agent" in existing_data:
            existing_agent = existing_data["agent"]
            agent_id = existing_agent.id
            typer.echo(f"Updating existing Agent (ID: {agent_id})...")
            agent_update_data = AgentUpdate(
                name=agent_name,
                description=description or existing_agent.description,
                agent_definition_id=definition_id,
                agent_type=agent_type,
                secrets=env_variables if env_variables else None
            )
            updated_agent = client.update_agent(agent_id, agent_update_data)
            typer.secho(f"Agent '{updated_agent.name}' updated (ID: {updated_agent.id}).", fg=typer.colors.GREEN)
        else:
            typer.echo(f"Creating new Agent linked to definition {definition_id}...")
            agent_payload = AgentCreate(
                name=agent_name,
                description=description,
                agent_type=agent_type,
                agent_definition_id=definition_id,
                secrets=env_variables if env_variables else None
            )
            created_agent = client.create_agent(agent_payload)
            agent_id = created_agent.id
            typer.secho(f"Agent '{created_agent.name}' created (ID: {agent_id}).", fg=typer.colors.GREEN)
    
    # Save state
    state_data = {
        "agent_name": agent_name,
        "agent_definition_id": str(definition_id) if definition_id else None,
        "agent_id": str(agent_id) if agent_id else None,
        "last_deploy_mode": deploy_mode,
        "last_deployed_at": datetime.now().isoformat()
    }
    save_project_state(state_data, project_dir)
    
    typer.secho("Bundle deployment completed successfully!", fg=typer.colors.GREEN)
    if definition_id:
        typer.echo(f"  Definition ID: {definition_id}")
    if agent_id:
        typer.echo(f"  Agent ID: {agent_id}")
    typer.echo(f"  Project state saved to {project_dir / PROJECT_STATE_FILE}")

# --- Typer App ---
app = typer.Typer(
    name="dlm",
    help="DantaLabs Maestro CLI - Interact with the Maestro service.",
    add_completion=False,
)
state = {"client": None, "config": None} 

# --- Modified get_client ---
def get_client(
    org_id_opt: Annotated[Optional[UUID], typer.Option("--org-id", "--organization-id", help="Maestro Organization ID (Overrides config file & env var).")] = None,
    base_url_opt: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides config file & env var).")] = None,
    token_opt: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides config file & env var).")] = None,
    agent_id_opt: Annotated[Optional[UUID], typer.Option("--agent-id", help="Maestro Agent ID (Overrides config file & env var).")] = None,
) -> MaestroClient:
    """
    Creates and returns a MaestroClient, handling configuration precedence:
    1. Command-line options (--org-id, --url, --token, --agent-id)
    2. Configuration file (~/.maestro/config.json)
    3. Environment variables (MAESTRO_ORGANIZATION_ID, etc.)
    """
    if state.get("client"):
        return state["client"]

    # Load config file only once per run if needed
    if state.get("config") is None:
         state["config"] = load_config()
    config = state["config"]

    org_id = org_id_opt or config.get("organization_id") or os.getenv("MAESTRO_ORGANIZATION_ID")
    base_url = base_url_opt or config.get("base_url") or os.getenv("MAESTRO_API_URL")
    token = token_opt or config.get("token") or os.getenv("MAESTRO_AUTH_TOKEN")
    agent_id = agent_id_opt or config.get("agent_id") or os.getenv("MAESTRO_AGENT_ID")

    if not org_id:
        typer.secho("Error: Organization ID not found. Use 'dlm setup', set MAESTRO_ORGANIZATION_ID, or use --org-id.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if not base_url:
        typer.secho("Error: Maestro API URL not found. Use 'dlm setup', set MAESTRO_API_URL, or use --url.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if not token:
         typer.secho("Error: Auth Token not found. Use 'dlm setup', set MAESTRO_AUTH_TOKEN, or use --token.", fg=typer.colors.RED, err=True)
         raise typer.Exit(code=1)

    try:
        client = MaestroClient(
            organization_id=str(org_id),
            base_url=base_url,
            token=token,
            agent_id=agent_id,
            raise_for_status=True
        )
        state["client"] = client
        return client
    except (ValueError, MaestroAuthError) as e:
        typer.secho(f"Error initializing client: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except MaestroApiError as e:
         typer.secho(f"Error connecting to API ({e.status_code}): {e.error_detail}", fg=typer.colors.RED, err=True)
         raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"An unexpected error occurred during client initialization: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

# --- NEW Setup Command ---
@app.command()
def setup(
    base_url_arg: Annotated[Optional[str], typer.Option("--url", help="Set Maestro API Base URL non-interactively.")] = None,
    org_id_arg: Annotated[Optional[str], typer.Option("--org-id", help="Set Maestro Organization ID non-interactively.")] = None,
    token_arg: Annotated[Optional[str], typer.Option("--token", help="Set Maestro Auth Token non-interactively.")] = None,
    email_arg: Annotated[Optional[str], typer.Option("--email", help="Set email address for token verification non-interactively.")] = None,
):
    """
    Configure Maestro CLI settings (Org ID, Token) interactively.

    Stores configuration in ~/.maestro/config.json.
    Values can be passed non-interactively via options.
    """
    typer.secho(f"Configuring Maestro CLI settings (saving to {CONFIG_FILE})...", fg=typer.colors.CYAN)

    # Load existing config to show as defaults
    config = load_config()

    # Use default base URL or argument if provided, no interactive prompt
    base_url = base_url_arg or config.get("base_url", "https://dantalabs.com")
    
    # Get token first as we'll need it to verify with email
    token = token_arg
    if token is None:
        default_token_display = "****" if config.get("token") else None
        token = typer.prompt("Enter Maestro Auth Token", default=default_token_display, hide_input=True)
        # If user just presses Enter on the hidden prompt with a default, keep the old token
        if token == default_token_display and config.get("token"):
            token = config.get("token")

    if not token:
        typer.secho("Error: Token cannot be empty.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Handle org_id: use provided value or verify with email
    org_id = org_id_arg
    if org_id is None:
        # Get email for verification
        email = email_arg
        if email is None:
            email = typer.prompt("Enter your registered email address")
        
        if not email:
            typer.secho("Error: Email cannot be empty for token verification.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        
        # Create a temporary client for verification
        temp_client = None
        try:
            # We need a client with a dummy organization ID just to make the verification request
            temp_client = MaestroClient(
                organization_id=str(UUID(int=0)),  # Temporary dummy UUID
                base_url=base_url,
                token=token,
                raise_for_status=True
            )
            
            typer.echo(f"Verifying token for email: {email}...")
            result = temp_client.verify_token_with_email(email, token)
            
            # Extract organization ID from the response
            if result and "organization_id" in result:
                org_id = result["organization_id"]
                typer.echo(f"Successfully verified token. Organization ID: {org_id}")
            else:
                typer.secho("Error: Could not retrieve organization ID from verification response.", fg=typer.colors.RED, err=True)
                typer.secho("Response: " + str(result), fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
                
        except MaestroAuthError:
            typer.secho("Authentication failed. Please check your token and email.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        except MaestroApiError as e:
            typer.secho(f"API Error verifying token: {e}", fg=typer.colors.RED, err=True)
            # Fall back to manual entry
            org_id = typer.prompt("Enter Maestro Organization ID manually", default=config.get("organization_id", None))
        except Exception as e:
            typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
            # Fall back to manual entry
            org_id = typer.prompt("Enter Maestro Organization ID manually", default=config.get("organization_id", None))
        finally:
            if temp_client:
                temp_client.close()
    
    if not base_url:
        typer.secho("Error: Base URL cannot be empty.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if not org_id:
        typer.secho("Error: Organization ID cannot be empty.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    if not token:
        typer.secho("Error: Token cannot be empty.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # --- Security Warning ---
    typer.secho("\nWarning: The authentication token will be stored in plain text in", fg=typer.colors.YELLOW, nl=False)
    typer.secho(f" {CONFIG_FILE}", fg=typer.colors.WHITE, bold=True)
    typer.secho("Ensure this file is adequately protected.", fg=typer.colors.YELLOW)

    # Prepare new config data
    new_config = {
        "base_url": base_url,
        "organization_id": str(org_id), 
        "token": token,
    }

    # Save the configuration
    save_config(new_config)

    typer.secho("\nConfiguration saved successfully!", fg=typer.colors.GREEN)
    typer.echo(f" Base URL: {new_config['base_url']}")
    typer.echo(f" Org ID:   {new_config['organization_id']}")
    typer.echo(f" Token:    **** (Set)")

@app.command()
def deploy(
    file_path: Annotated[Optional[Path], typer.Argument(
        help="Path to the Python file or directory containing agent code. If not provided, uses current directory.",
    )] = None,
    name: Annotated[Optional[str], typer.Option(
        "--name", "-n",
        help="Name for the Agent Definition and Agent. Defaults to the filename or directory name."
    )] = None,
    description: Annotated[Optional[str], typer.Option(
        "--desc", "-d",
        help="Optional description for the Agent Definition."
    )] = None,
    agent_type: Annotated[str, typer.Option(
        "--agent-type", "-t",
        help="Type of the agent (e.g., 'script', 'chat', 'tool')."
    )] = "script", 
    force_mode: Annotated[Optional[str], typer.Option(
        "--mode",
        help="Force deployment mode: 'create', 'update', or 'redeploy'. Auto-detected if not specified."
    )] = None,
    create_agent: Annotated[bool, typer.Option(
        "--create-agent/--definition-only",
        help="Create/update an Agent instance linked to the definition (default: True).",
    )] = True,
    schema_file: Annotated[Optional[Path], typer.Option(
        "--schema-file", 
        help="Path to a JSON file containing input/output/memory schemas. Auto-detected if not specified."
    )] = None,
    env_file: Annotated[Optional[Path], typer.Option(
        "--env-file", 
        help="Path to a .env file containing environment variables. Auto-detected if not specified."
    )] = None,
    # Add shared options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,

):
    """
    Intelligently deploys agent code as a Maestro Agent Definition and Agent.
    
    Automatically detects whether to create, update, or redeploy based on existing state.
    Supports both single Python files and directory-based agent bundles.
    Automatically loads schemas and environment variables from conventional locations.
    """
    client = get_client(org_id, url, token)
    
    # Handle file_path - if not provided, use current directory
    if file_path is None:
        file_path = Path.cwd()
    
    # Validate path exists
    if not file_path.exists():
        typer.secho(f"Error: Path '{file_path}' does not exist.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    # Determine if we're dealing with a file or directory
    is_bundle = file_path.is_dir()
    project_dir = file_path if is_bundle else file_path.parent
    
    # Determine agent name
    if is_bundle:
        agent_name = name or file_path.name
        typer.echo(f"Deploying agent bundle from '{file_path}' as '{agent_name}'...")
    else:
        if not file_path.is_file() or not file_path.suffix == '.py':
            typer.secho(f"Error: File path must be a Python file (.py) or a directory.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        agent_name = name or file_path.stem
        typer.echo(f"Deploying agent from '{file_path.name}' as '{agent_name}'...")
    
    # Determine deployment mode
    deploy_mode, existing_data = get_deploy_mode(client, agent_name, project_dir)
    if force_mode:
        if force_mode not in ["create", "update", "redeploy"]:
            typer.secho(f"Error: Invalid mode '{force_mode}'. Must be 'create', 'update', or 'redeploy'.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        deploy_mode = force_mode
        typer.echo(f"Using forced deployment mode: {deploy_mode}")
    else:
        typer.echo(f"Auto-detected deployment mode: {deploy_mode}")

    # Handle bundle vs single file deployment
    if is_bundle:
        # Use bundle deployment for directories
        return deploy_bundle_with_state(
            client=client,
            source_dir=file_path,
            agent_name=agent_name,
            description=description,
            agent_type=agent_type,
            deploy_mode=deploy_mode,
            existing_data=existing_data,
            create_agent=create_agent,
            schema_file=schema_file,
            env_file=env_file,
            project_dir=project_dir
        )
    
    # Single file deployment
    try:
        agent_code = file_path.read_text()
    except Exception as e:
        typer.secho(f"Error reading file '{file_path}': {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    # Load schemas and environment variables
    input_schema, output_schema, memory_template = load_schemas(file_path, schema_file)
    env_variables = load_env_variables(file_path.parent, env_file)

    # Deploy based on mode
    definition_id, agent_id = deploy_single_file(
        client=client,
        agent_code=agent_code,
        agent_name=agent_name,
        description=description,
        agent_type=agent_type,
        deploy_mode=deploy_mode,
        existing_data=existing_data,
        create_agent=create_agent,
        input_schema=input_schema,
        output_schema=output_schema,
        memory_template=memory_template,
        env_variables=env_variables
    )
    
    # Save state for future deployments
    state_data = {
        "agent_name": agent_name,
        "agent_definition_id": str(definition_id) if definition_id else None,
        "agent_id": str(agent_id) if agent_id else None,
        "last_deploy_mode": deploy_mode,
        "last_deployed_at": datetime.now().isoformat()
    }
    save_project_state(state_data, project_dir)
    
    typer.secho("Deployment completed successfully!", fg=typer.colors.GREEN)
    if definition_id:
        typer.echo(f"  Definition ID: {definition_id}")
    if agent_id:
        typer.echo(f"  Agent ID: {agent_id}")
    typer.echo(f"  Project state saved to {project_dir / PROJECT_STATE_FILE}")

@app.command(name="list-agents")
def list_agents_cmd(
    show_definition: Annotated[bool, typer.Option(
        "--show-def", 
        help="Show agent definition information"
    )] = False,
    # Add shared options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """
    List all agents in the current organization.
    """
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

@app.command(name="list-definitions")
def list_definitions_cmd(
    # Add shared options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """
    List all agent definitions in the current organization.
    """
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

@app.command()
def status(
    # Add shared options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """
    Show status of the current project and connected agents.
    """
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

@app.command()
def create_agent(
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
    # Add shared options via dependencies= parameter or manually
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
    env_file: Annotated[Optional[Path], typer.Option(
        "--env-file", help="Path to a .env file containing environment variables as secrets."
    )] = None,
):
    """
    Creates a new Maestro Agent from an existing Agent Definition.
    
    If no Agent Definition ID is provided, lists available definitions and prompts for selection.
    Automatically loads secrets from .env file in current directory if no env_file specified.
    """
    client = get_client(org_id, url, token) # Use the helper to get configured client
    
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
        except Exception as e:
            typer.secho(f"Unexpected error: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    # If name not provided, prompt for it
    agent_name = name
    if not agent_name:
        agent_name = typer.prompt("Enter agent name")
    
    # If agent_type not provided, prompt for it
    agent_type_value = agent_type
    if not agent_type_value:
        agent_type_value = typer.prompt("Enter agent type (e.g., script, chat, tool)", default="script")
    
    # Load secrets from .env file if provided
    secrets = {}
    
    # If env_file not provided, try to use .env in current directory
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
            else:
                typer.echo("No secrets found in .env file.")
        except Exception as e:
            typer.secho(f"Error reading .env file '{env_file}': {e}", fg=typer.colors.YELLOW, err=True)
            typer.secho("Continuing without secrets.", fg=typer.colors.YELLOW)
    
    # Create the agent
    try:
        typer.echo(f"Creating agent '{agent_name}' with definition ID {definition_id}...")
        
        agent_payload = AgentCreate(
            name=agent_name,
            description=description,
            agent_type=agent_type_value,
            agent_definition_id=definition_id,
            secrets=secrets or None,
            # Default fields: capabilities=[], agent_metadata={}
        )
        
        
        created_agent = client.create_agent(agent_payload)
        typer.secho(f"Agent '{created_agent.name}' created successfully (ID: {created_agent.id}).", fg=typer.colors.GREEN)
        
    except (MaestroValidationError, MaestroApiError) as e:
        typer.secho(f"API Error creating agent: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"Unexpected error during agent creation: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def update_agent(
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
    # Add shared options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var)")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var)")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var)")] = None,
):
    """
    Updates an existing Maestro Agent with new properties.
    
    If no agent_id is provided, uses the agent set with 'use_agent' command.
    Only provided fields will be updated.
    Automatically loads secrets from .env file in current directory if no env_file specified.
    """
    client = get_client(org_id, url, token)
    
    # Resolve agent_id
    agent_id_to_use = None
    if agent_id:
        agent_id_to_use = agent_id
    elif client.agent_id:
        agent_id_to_use = client.agent_id
        config = load_config()
        agent_name = config.get("agent_name", "Default Agent")
        typer.echo(f"Using default agent: {agent_name} (ID: {agent_id_to_use})")
    else:
        typer.secho("Error: No agent ID provided or set. Use agent_id argument or 'dlm use_agent' first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    # Fetch current agent to show values being updated
    try:
        current_agent = client.get_agent(agent_id_to_use)
        typer.echo(f"Updating agent: {current_agent.name} (ID: {agent_id_to_use})")
    except MaestroApiError as e:
        typer.secho(f"Warning: Could not fetch current agent details: {e}", fg=typer.colors.YELLOW, err=True)
        typer.echo("Continuing with update...")
        current_agent = None
    
    # Load secrets from .env file if provided or use default
    secrets = None
    
    # If env_file not provided, try to use .env in current directory
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
            else:
                typer.echo("No secrets found in .env file.")
        except Exception as e:
            typer.secho(f"Error reading .env file '{env_file}': {e}", fg=typer.colors.YELLOW, err=True)
            typer.secho("Continuing without updating secrets.", fg=typer.colors.YELLOW)
    
    # Prepare update data, only including fields that are provided
    update_data = {}
    if name is not None:
        update_data["name"] = name
        if current_agent:
            typer.echo(f"Updating name: '{current_agent.name}' -> '{name}'")
    
    if description is not None:
        update_data["description"] = description
        if current_agent:
            typer.echo(f"Updating description: '{current_agent.description or 'None'}' -> '{description}'")
    
    if agent_type is not None:
        update_data["agent_type"] = agent_type
        if current_agent:
            typer.echo(f"Updating agent type: '{current_agent.agent_type}' -> '{agent_type}'")
    
    if definition_id is not None:
        update_data["agent_definition_id"] = str(definition_id)
        if current_agent:
            typer.echo(f"Updating definition ID: '{current_agent.agent_definition_id}' -> '{definition_id}'")
    
    if secrets is not None:
        update_data["secrets"] = secrets
        typer.echo("Updating agent secrets from env file")
    
    # If no fields to update, exit
    if not (name or description or agent_type or definition_id or secrets):
        typer.secho("No fields to update. Provide at least one field to change.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)
    
    # Update the agent
    try:
        # Create an AgentUpdate model
        agent_update = AgentUpdate(
            name=name,
            description=description,
            agent_type=agent_type,
            agent_definition_id=definition_id,
            secrets=secrets
        )
        
        updated_agent = client.update_agent(agent_id_to_use, agent_update)
        typer.secho(f"Agent '{updated_agent.name}' updated successfully.", fg=typer.colors.GREEN)
        return updated_agent
        
    except (MaestroValidationError, MaestroApiError) as e:
        typer.secho(f"API Error updating agent: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"Unexpected error during agent update: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def use_agent(
    agent_id: Annotated[Optional[str], typer.Argument(help="Agent ID to use for this session")] = None,
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Optional agent name for reference")] = None,
    # Add shared options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """
    Set the default agent to use for subsequent commands.
    
    Stores the agent ID in the configuration for use by other commands.
    If no agent_id is provided, lists available agents and prompts for selection.
    """
    # Load config
    config = load_config()
    client = get_client(org_id, url, token)
    
    # If no agent_id provided, list agents and prompt for selection
    if not agent_id:
        try:
            typer.echo("Fetching available agents...")
            agents = client.list_agents()
            
            if not agents:
                typer.secho("No agents found. Create one first using 'dlm create_agent'.", fg=typer.colors.RED, err=True)
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
        except Exception as e:
            typer.secho(f"Unexpected error: {e}", fg=typer.colors.RED, err=True)
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
            if not name:
                typer.echo("Continuing with unverified agent ID...")
        except Exception as e:
            typer.secho(f"Warning: Error verifying agent: {e}", fg=typer.colors.YELLOW, err=True)
            agent_name = name or "Unknown"
    
    # Update configuration
    config["agent_id"] = str(agent_id_uuid)
    if name or agent_name:
        config["agent_name"] = name or agent_name
    
    # Save configuration
    save_config(config)
    
    typer.secho(f"Default agent set to: {agent_name} (ID: {agent_id_uuid})", fg=typer.colors.GREEN)
    typer.echo("This agent will be used for future commands unless overridden.")

@app.command()
def run_agent(
    input_json: Annotated[Optional[str], typer.Argument(help="JSON string of input variables or path to JSON file")] = None,
    agent_id: Annotated[Optional[str], typer.Option("--agent-id", "-a", help="Agent ID to run (overrides default agent)")] = None,
    executor_type: Annotated[Optional[str], typer.Option("--executor", "-e", help="Executor type (e.g., modal, azure)")] = None,
    input_file: Annotated[Optional[Path], typer.Option("--file", "-f", help="Path to JSON file containing input variables")] = None,
    # Add shared options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """
    Run an agent synchronously with provided input variables.
    
    Input can be provided as a JSON string directly, or as a path to a JSON file.
    If no agent_id is provided, uses the agent set with 'use_agent' command.
    """
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
        except Exception as e:
            typer.secho(f"Error reading input file '{input_file}': {e}", fg=typer.colors.RED, err=True)
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
            except Exception as e:
                typer.secho(f"Error reading input file '{potential_file}': {e}", fg=typer.colors.RED, err=True)
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
        typer.secho("Error: No agent ID provided or set. Use --agent-id or 'dlm use_agent' first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    # Execute the agent code
    try:
        typer.echo(f"Running agent {agent_id_to_use} with sync execution...")
        execution = client.execute_agent_code_sync(
            variables=input_variables,
            agent_id=agent_id_to_use,
            executor_type=executor_type
        )
        
        # Display results
        typer.secho("Execution completed successfully!", fg=typer.colors.GREEN)
        # typer.echo(f"Execution ID: {execution.id}")
        # typer.echo(f"Status: {execution.status}")
        
        # Display output if available
        # if execution.output:
        #     typer.secho("\nOutput:", fg=typer.colors.CYAN)
        #     if isinstance(execution.output, dict):
        #         # Pretty print if the output is a dictionary
        #         typer.echo(json.dumps(execution.output, indent=2))
        #     else:
        #         typer.echo(execution.output)
        
        # # Display errors if any
        # if execution.error:
        #     typer.secho("\nErrors:", fg=typer.colors.RED)
        #     typer.echo(execution.error)
        
        # # Return the execution object
        return execution
        
    except MaestroApiError as e:
        typer.secho(f"API Error executing agent: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"Unexpected error during agent execution: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def create_bundle(
    source_dir: Annotated[Path, typer.Argument(
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to the directory containing the agent code.",
    )],
    output_path: Annotated[Optional[Path], typer.Option(
        "--output", "-o",
        help="Output path for the bundle ZIP file. If not provided, creates in temp directory."
    )] = None,
    name: Annotated[Optional[str], typer.Option(
        "--name", "-n",
        help="Name for the agent (used for maestro.yaml if not present)."
    )] = None,
    description: Annotated[Optional[str], typer.Option(
        "--desc", "-d",
        help="Description for the agent (used for maestro.yaml if not present)."
    )] = None,
    entrypoint: Annotated[Optional[str], typer.Option(
        "--entrypoint", "-e",
        help="Entrypoint file for the agent (default: main.py)."
    )] = "main.py",
    version: Annotated[Optional[str], typer.Option(
        "--version", "-v",
        help="Version for the agent (default: 1.0.0)."
    )] = "1.0.0",
    no_requirements: Annotated[bool, typer.Option(
        "--no-requirements",
        help="Skip automatic inclusion of requirements from pyproject.toml or requirements.txt."
    )] = False,
    no_install_deps: Annotated[bool, typer.Option(
        "--no-install-deps",
        help="Skip automatic installation of dependencies into the bundle. Only include requirements.txt instead."
    )] = False,
    # Add shared options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """
    Create a ZIP bundle from a source directory for agent deployment.
    
    The bundle will include all files from the source directory and automatically
    install dependencies from pyproject.toml or requirements.txt files if found.
    Dependencies are installed directly into the bundle as Python libraries.
    """
    client = get_client(org_id, url, token)
    
    # Determine bundle name
    bundle_name = name or source_dir.name
    
    # Create maestro config
    maestro_config = {
        "entrypoint": entrypoint,
        "description": description or f"Bundle for {bundle_name}",
        "version": version
    }
    
    try:
        typer.echo(f"Creating bundle from '{source_dir}'...")
        
        bundle_path = client.create_bundle(
            source_dir=str(source_dir),
            output_path=str(output_path) if output_path else None,
            include_requirements=not no_requirements,
            install_dependencies=not no_install_deps,
            maestro_config=maestro_config
        )
        
        typer.secho(f"Bundle created successfully: {bundle_path}", fg=typer.colors.GREEN)
        
        # Show bundle info
        import zipfile
        with zipfile.ZipFile(bundle_path, 'r') as zipf:
            file_count = len(zipf.namelist())
            typer.echo(f"Bundle contains {file_count} files:")
            for filename in sorted(zipf.namelist())[:10]:  # Show first 10 files
                typer.echo(f"  - {filename}")
            if file_count > 10:
                typer.echo(f"  ... and {file_count - 10} more files")
        
    except Exception as e:
        typer.secho(f"Error creating bundle: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def upload_bundle(
    bundle_path: Annotated[Path, typer.Argument(
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to the ZIP bundle file to upload.",
    )],
    name: Annotated[str, typer.Option(
        "--name", "-n",
        help="Name for the Agent Definition."
    )],
    description: Annotated[Optional[str], typer.Option(
        "--desc", "-d",
        help="Optional description for the Agent Definition."
    )] = None,
    entrypoint: Annotated[str, typer.Option(
        "--entrypoint", "-e",
        help="Main entry point file for the bundle."
    )] = "main.py",
    version: Annotated[str, typer.Option(
        "--version", "-v",
        help="Version of the bundle."
    )] = "1.0.0",
    requirements_file: Annotated[Optional[Path], typer.Option(
        "--requirements-file",
        help="Path to a requirements.txt file to include as bundle requirements."
    )] = None,
    schema_file: Annotated[Optional[Path], typer.Option(
        "--schema-file",
        help="Path to a JSON file containing input/output schemas."
    )] = None,
    metadata_file: Annotated[Optional[Path], typer.Option(
        "--metadata-file",
        help="Path to a JSON file containing additional metadata."
    )] = None,
    shareable: Annotated[bool, typer.Option(
        "--shareable/--no-shareable",
        help="Whether the agent definition is shareable."
    )] = False,
    create_agent_flag: Annotated[bool, typer.Option(
        "--create-agent/--no-create-agent",
        help="Create an Agent instance linked to the definition."
    )] = False,
    agent_type: Annotated[str, typer.Option(
        "--agent-type", "-t",
        help="Type of the agent (required if creating an agent)."
    )] = "script",
    env_file: Annotated[Optional[Path], typer.Option(
        "--env-file",
        help="Path to a .env file containing environment variables as secrets."
    )] = None,
    # Add shared options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
    timeout: Annotated[Optional[int], typer.Option(
        "--upload-timeout",
        help="Timeout in seconds for the upload bundle request (default: 600)."
    )] = None,
):
    """
    Upload a ZIP bundle to create a new Agent Definition.
    
    The bundle should contain agent code and optionally a maestro.yaml configuration file.
    """
    client = get_client(org_id, url, token)
    
    # Load schemas if provided
    input_schema = {}
    output_schema = {}
    
    if schema_file and schema_file.exists():
        try:
            typer.echo(f"Loading schemas from '{schema_file}'...")
            with open(schema_file, 'r') as f:
                schema_data = json.load(f)
            
            input_schema = schema_data.get('input', {})
            output_schema = schema_data.get('output', {})
            
            if input_schema:
                typer.echo("Input schema loaded.")
            if output_schema:
                typer.echo("Output schema loaded.")
                
        except json.JSONDecodeError as e:
            typer.secho(f"Error parsing JSON file '{schema_file}': {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        except Exception as e:
            typer.secho(f"Error reading schema file '{schema_file}': {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    # Load requirements if provided
    requirements = None
    if requirements_file and requirements_file.exists():
        try:
            typer.echo(f"Loading requirements from '{requirements_file}'...")
            with open(requirements_file, 'r') as f:
                requirements_content = f.read().strip()
            requirements = [req.strip() for req in requirements_content.split('\n') if req.strip()]
            typer.echo(f"Loaded {len(requirements)} requirements.")
        except Exception as e:
            typer.secho(f"Error reading requirements file '{requirements_file}': {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    # Load additional metadata if provided
    additional_metadata = None
    if metadata_file and metadata_file.exists():
        try:
            typer.echo(f"Loading additional metadata from '{metadata_file}'...")
            with open(metadata_file, 'r') as f:
                additional_metadata = json.load(f)
            typer.echo("Additional metadata loaded.")
        except json.JSONDecodeError as e:
            typer.secho(f"Error parsing JSON file '{metadata_file}': {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        except Exception as e:
            typer.secho(f"Error reading metadata file '{metadata_file}': {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    try:
        typer.echo(f"Uploading bundle '{bundle_path.name}' as Agent Definition '{name}'...")
        timeout_value = timeout if timeout else 600
        typer.echo(f"This may take several minutes... (timeout: {timeout_value} seconds)")
        
        agent_definition = client.upload_agent_bundle(
            bundle_path=str(bundle_path),
            name=name,
            description=description,
            input_schema=input_schema if input_schema else None,
            output_schema=output_schema if output_schema else None,
            entrypoint=entrypoint,
            version=version,
            requirements=requirements,
            additional_metadata=additional_metadata,
            shareable=shareable,
            upload_timeout=timeout if timeout else 600.0
        )
        
        typer.secho(f"Agent Definition '{agent_definition.name}' created successfully (ID: {agent_definition.id})", fg=typer.colors.GREEN)
        
        # Create agent if requested
        if create_agent_flag:
            # Load secrets from .env file if provided
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
            
            try:
                typer.echo(f"Creating agent '{name}' with definition ID {agent_definition.id}...")
                
                agent_payload = AgentCreate(
                    name=name,
                    description=description,
                    agent_type=agent_type,
                    agent_definition_id=agent_definition.id,
                    secrets=secrets if secrets else None
                )
                
                created_agent = client.create_agent(agent_payload)
                typer.secho(f"Agent '{created_agent.name}' created successfully (ID: {created_agent.id})", fg=typer.colors.GREEN)
                
            except Exception as e:
                typer.secho(f"Error creating agent: {e}", fg=typer.colors.YELLOW, err=True)
                typer.echo("Agent Definition was created successfully, but agent creation failed.")
        
    except Exception as e:
        typer.secho(f"Error uploading bundle: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def deploy_bundle(
    source_dir: Annotated[Path, typer.Argument(
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Path to the directory containing the agent code.",
    )],
    name: Annotated[Optional[str], typer.Option(
        "--name", "-n",
        help="Name for the Agent Definition and Agent. Defaults to the directory name."
    )] = None,
    description: Annotated[Optional[str], typer.Option(
        "--desc", "-d",
        help="Optional description for the Agent Definition."
    )] = None,
    entrypoint: Annotated[Optional[str], typer.Option(
        "--entrypoint", "-e",
        help="Entrypoint file for the agent (default: main.py)."
    )] = "main.py",
    version: Annotated[Optional[str], typer.Option(
        "--version", "-v",
        help="Version for the agent (default: 1.0.0)."
    )] = "1.0.0",
    schema_file: Annotated[Optional[Path], typer.Option(
        "--schema-file",
        help="Path to a JSON file containing input/output schemas."
    )] = None,
    requirements_file: Annotated[Optional[Path], typer.Option(
        "--requirements-file",
        help="Path to a requirements.txt file to include as bundle requirements."
    )] = None,
    metadata_file: Annotated[Optional[Path], typer.Option(
        "--metadata-file",
        help="Path to a JSON file containing additional metadata."
    )] = None,
    shareable: Annotated[bool, typer.Option(
        "--shareable/--no-shareable",
        help="Whether the agent definition is shareable."
    )] = False,
    create_agent_flag: Annotated[bool, typer.Option(
        "--create-agent/--no-create-agent",
        help="Create an Agent instance linked to the definition."
    )] = True,
    agent_type: Annotated[str, typer.Option(
        "--agent-type", "-t",
        help="Type of the agent."
    )] = "script",
    env_file: Annotated[Optional[Path], typer.Option(
        "--env-file",
        help="Path to a .env file containing environment variables as secrets."
    )] = None,
    no_requirements: Annotated[bool, typer.Option(
        "--no-requirements",
        help="Skip automatic inclusion of requirements from pyproject.toml or requirements.txt."
    )] = False,
    no_install_deps: Annotated[bool, typer.Option(
        "--no-install-deps",
        help="Skip automatic installation of dependencies into the bundle. Only include requirements.txt instead."
    )] = False,
    # Add shared options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
    timeout: Annotated[Optional[int], typer.Option(
        "--upload-timeout",
        help="Timeout in seconds for the upload bundle request (default: 600)."
    )] = None,
):
    """
    Create and deploy a bundle from a source directory in one command.
    
    This combines bundle creation and upload into a single operation.
    Automatically loads schemas and secrets from the source directory.
    Dependencies are installed directly into the bundle as Python libraries.
    """
    client = get_client(org_id, url, token)
    
    # Determine agent name
    agent_name = name or source_dir.name
    
    # Load schemas if provided or look for default
    input_schema = {}
    output_schema = {}
    
    if not schema_file:
        default_schema_file = source_dir / f"{agent_name}.json"
        if default_schema_file.exists():
            schema_file = default_schema_file
    
    if schema_file and schema_file.exists():
        try:
            typer.echo(f"Loading schemas from '{schema_file}'...")
            with open(schema_file, 'r') as f:
                schema_data = json.load(f)
            
            input_schema = schema_data.get('input', {})
            output_schema = schema_data.get('output', {})
            
            if input_schema:
                typer.echo("Input schema loaded.")
            if output_schema:
                typer.echo("Output schema loaded.")
                
        except Exception as e:
            typer.secho(f"Error loading schemas: {e}", fg=typer.colors.YELLOW, err=True)
            typer.echo("Continuing without schemas.")
    
    # Load requirements if provided or look for default
    requirements = None
    if not requirements_file and not no_requirements:
        # Look for default requirements files in source directory
        default_req_file = source_dir / 'requirements.txt'
        if default_req_file.exists():
            requirements_file = default_req_file
    
    if requirements_file and requirements_file.exists():
        try:
            typer.echo(f"Loading requirements from '{requirements_file}'...")
            with open(requirements_file, 'r') as f:
                requirements_content = f.read().strip()
            requirements = [req.strip() for req in requirements_content.split('\n') if req.strip()]
            typer.echo(f"Loaded {len(requirements)} requirements.")
        except Exception as e:
            typer.secho(f"Error reading requirements file '{requirements_file}': {e}", fg=typer.colors.YELLOW, err=True)
            typer.echo("Continuing without explicit requirements.")
    
    # Load additional metadata if provided
    additional_metadata = None
    if metadata_file and metadata_file.exists():
        try:
            typer.echo(f"Loading additional metadata from '{metadata_file}'...")
            with open(metadata_file, 'r') as f:
                additional_metadata = json.load(f)
            typer.echo("Additional metadata loaded.")
        except Exception as e:
            typer.secho(f"Error loading additional metadata: {e}", fg=typer.colors.YELLOW, err=True)
            typer.echo("Continuing without additional metadata.")
    
    # Load secrets from .env file
    secrets = {}
    
    if not env_file:
        default_env_file = source_dir / '.env'
        if default_env_file.exists():
            env_file = default_env_file
    
    if env_file and env_file.exists():
        try:
            typer.echo(f"Loading secrets from '{env_file}'...")
            secrets = dotenv.dotenv_values(env_file)
            if secrets:
                typer.echo(f"Loaded {len(secrets)} secrets.")
        except Exception as e:
            typer.secho(f"Error reading .env file '{env_file}': {e}", fg=typer.colors.YELLOW, err=True)
    
    # Create maestro config
    maestro_config = {
        "entrypoint": entrypoint,
        "description": description or f"Bundle for {agent_name}",
        "version": version
    }
    
    try:
        typer.echo(f"Creating and deploying bundle from '{source_dir}' as '{agent_name}'...")
        timeout_value = timeout if timeout else 600
        typer.echo(f"This includes dependency installation and upload, which may take several minutes... (upload timeout: {timeout_value} seconds)")
        
        agent_definition = client.create_and_upload_bundle(
            source_dir=str(source_dir),
            name=agent_name,
            description=description,
            input_schema=input_schema if input_schema else None,
            output_schema=output_schema if output_schema else None,
            entrypoint=entrypoint,
            version=version,
            requirements=requirements,
            additional_metadata=additional_metadata,
            shareable=shareable,
            include_requirements=not no_requirements,
            install_dependencies=not no_install_deps,
            maestro_config=maestro_config,
            upload_timeout=timeout if timeout else 600.0
        )
        
        typer.secho(f"Agent Definition '{agent_definition.name}' created successfully (ID: {agent_definition.id})", fg=typer.colors.GREEN)
        
        # Create agent if requested
        if create_agent_flag:
            try:
                typer.echo(f"Creating agent '{agent_name}' with definition ID {agent_definition.id}...")
                
                agent_payload = AgentCreate(
                    name=agent_name,
                    description=description,
                    agent_type=agent_type,
                    agent_definition_id=agent_definition.id,
                    secrets=secrets if secrets else None
                )
                
                created_agent = client.create_agent(agent_payload)
                typer.secho(f"Agent '{created_agent.name}' created successfully (ID: {created_agent.id})", fg=typer.colors.GREEN)
                
            except Exception as e:
                typer.secho(f"Error creating agent: {e}", fg=typer.colors.YELLOW, err=True)
                typer.echo("Agent Definition was created successfully, but agent creation failed.")
        
    except Exception as e:
        typer.secho(f"Error deploying bundle: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def update_bundle(
    definition_id: Annotated[str, typer.Argument(help="Agent Definition ID to update")],
    bundle_path: Annotated[Path, typer.Argument(
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to the new ZIP bundle file.",
    )],
    entrypoint: Annotated[Optional[str], typer.Option(
        "--entrypoint", "-e",
        help="Update the main entry point file for the bundle."
    )] = None,
    version: Annotated[Optional[str], typer.Option(
        "--version", "-v",
        help="Update the version of the bundle."
    )] = None,
    requirements_file: Annotated[Optional[Path], typer.Option(
        "--requirements-file",
        help="Path to a requirements.txt file to update bundle requirements."
    )] = None,
    metadata_file: Annotated[Optional[Path], typer.Option(
        "--metadata-file",
        help="Path to a JSON file containing additional metadata to update."
    )] = None,
    # Add shared options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
    timeout: Annotated[Optional[int], typer.Option(
        "--upload-timeout",
        help="Timeout in seconds for the upload bundle request (default: 600)."
    )] = None,
):
    """
    Update an existing bundled Agent Definition with a new ZIP bundle and optional metadata.
    """
    client = get_client(org_id, url, token)
    
    try:
        # Validate definition_id is a UUID
        definition_uuid = UUID(definition_id)
    except ValueError:
        typer.secho(f"Error: '{definition_id}' is not a valid UUID.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    # Load requirements if provided
    requirements = None
    if requirements_file and requirements_file.exists():
        try:
            typer.echo(f"Loading requirements from '{requirements_file}'...")
            with open(requirements_file, 'r') as f:
                requirements_content = f.read().strip()
            requirements = [req.strip() for req in requirements_content.split('\n') if req.strip()]
            typer.echo(f"Loaded {len(requirements)} requirements.")
        except Exception as e:
            typer.secho(f"Error reading requirements file '{requirements_file}': {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    # Load additional metadata if provided
    additional_metadata = None
    if metadata_file and metadata_file.exists():
        try:
            typer.echo(f"Loading additional metadata from '{metadata_file}'...")
            with open(metadata_file, 'r') as f:
                additional_metadata = json.load(f)
            typer.echo("Additional metadata loaded.")
        except json.JSONDecodeError as e:
            typer.secho(f"Error parsing JSON file '{metadata_file}': {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        except Exception as e:
            typer.secho(f"Error reading metadata file '{metadata_file}': {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
    
    try:
        typer.echo(f"Updating Agent Definition {definition_uuid} with bundle '{bundle_path.name}'...")
        timeout_value = timeout if timeout else 600
        typer.echo(f"This may take several minutes... (timeout: {timeout_value} seconds)")
        
        updated_definition = client.update_agent_bundle(
            definition_id=definition_uuid,
            bundle_path=str(bundle_path),
            entrypoint=entrypoint,
            version=version,
            requirements=requirements,
            additional_metadata=additional_metadata,
            upload_timeout=timeout if timeout else 600.0
        )
        
        typer.secho(f"Agent Definition '{updated_definition.name}' updated successfully", fg=typer.colors.GREEN)
        
    except Exception as e:
        typer.secho(f"Error updating bundle: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def download_definition_bundle(
    definition_id: Annotated[str, typer.Argument(help="Agent Definition ID")],
    output_path: Annotated[Optional[Path], typer.Option(
        "--output", "-o",
        help="Output path for the downloaded bundle. Defaults to 'agent_definition_bundle.zip'"
    )] = None,
    # Add shared options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """
    Download the bundle for a specific Agent Definition.
    """
    client = get_client(org_id, url, token)
    
    try:
        # Validate definition_id is a UUID
        definition_uuid = UUID(definition_id)
    except ValueError:
        typer.secho(f"Error: '{definition_id}' is not a valid UUID.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    # Determine output path
    if output_path is None:
        output_path = Path("agent_definition_bundle.zip")
    
    try:
        typer.echo(f"Downloading bundle for Agent Definition {definition_uuid}...")
        
        bundle_data = client.download_agent_definition_bundle(definition_uuid)
        
        with open(output_path, 'wb') as f:
            f.write(bundle_data)
        
        typer.secho(f"Bundle downloaded successfully: {output_path}", fg=typer.colors.GREEN)
        
        # Show bundle info
        import zipfile
        with zipfile.ZipFile(output_path, 'r') as zipf:
            file_count = len(zipf.namelist())
            typer.echo(f"Downloaded bundle contains {file_count} files")
        
    except Exception as e:
        typer.secho(f"Error downloading bundle: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command()
def version():
    typer.echo(VERSION)

if __name__ == "__main__":
    app()

    
