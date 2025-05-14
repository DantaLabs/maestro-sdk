import typer
import os
import sys
import json 
from pathlib import Path
from typing import Optional, Annotated, Dict, Any
from uuid import UUID
import dotenv

from .maestro import MaestroClient
from .maestro.models import AgentDefinitionCreate, AgentCreate, AgentUpdate, Agent, AgentDefinition
from .maestro.exceptions import MaestroApiError, MaestroAuthError, MaestroValidationError

# --- Configuration File Handling ---
CONFIG_DIR = Path.home() / ".maestro"
CONFIG_FILE = CONFIG_DIR / "config.json"

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
    file_path: Annotated[Path, typer.Argument(
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Path to the Python file containing the agent code.",
    )],
    name: Annotated[Optional[str], typer.Option(
        "--name", "-n",
        help="Name for the Agent Definition and Agent. Defaults to the filename without extension."
    )] = None,
    description: Annotated[Optional[str], typer.Option(
        "--desc", "-d",
        help="Optional description for the Agent Definition."
    )] = None,
    agent_type: Annotated[str, typer.Option(
        "--agent-type", "-t",
        help="Type of the agent (e.g., 'script', 'chat', 'tool'). Required if creating an agent."
    )] = "script", 
    update: Annotated[bool, typer.Option(
        "--update", "-u",
        help="Update existing Agent Definition and Agent if found with the same name.",
    )] = False,
    create_agent_flag: Annotated[bool, typer.Option(
        "--create-agent/--no-create-agent", # Creates a boolean flag
        help="Create/update an Agent instance linked to the definition.",
    )] = False,
    schema_file: Annotated[Optional[Path], typer.Option(
        "--schema-file", 
        help="Path to a JSON file containing input/output/memory schemas. Defaults to [agent_name].json."
    )] = None,
    env_file: Annotated[Optional[Path], typer.Option(
        "--env-file", 
        help="Path to a .env file containing environment variables. Defaults to .env in the same directory."
    )] = None,
    # Add shared options via dependencies= parameter or manually
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,

):
    """
    Deploys a Python file as a Maestro Agent Definition and optionally an Agent.
    
    Automatically loads schemas from a JSON file with the same name as the Python file (if it exists).
    The JSON file should have keys: 'input', 'output', and 'memory'.
    
    Also loads environment variables from a .env file in the same directory.
    """
    client = get_client(org_id, url, token) # Use the helper to get configured client

    # Determine default name if not provided
    agent_name = name or file_path.stem # e.g., "agent_example" from "agent_example.py"
    typer.echo(f"Deploying agent from '{file_path.name}' as '{agent_name}'...")

    try:
        # Read the agent code
        agent_code = file_path.read_text()
    except Exception as e:
        typer.secho(f"Error reading file '{file_path}': {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    # Initialize the schemas and environment variables
    input_schema = {}
    output_schema = {}
    memory_template = {}
    env_variables = {}
    
    # Try to load schemas from JSON file with same name if no specific file is provided
    if not schema_file:
        default_schema_file = file_path.with_suffix('.json')
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
    
    # Try to load environment variables from .env file
    if not env_file:
        default_env_file = file_path.parent / '.env'
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

    existing_definition: Optional[AgentDefinition] = None
    existing_agent: Optional[Agent] = None

    # --- Check for Existing Definition ---
    try:
        typer.echo(f"Checking for existing definition named '{agent_name}'...")
        all_definitions = client.list_agent_definitions() # TODO: Optimize if API supports filtering by name
        existing_definition = next((d for d in all_definitions if d.name == agent_name), None)
    except MaestroApiError as e:
         typer.secho(f"API Error checking for definition: {e}", fg=typer.colors.RED, err=True)
         raise typer.Exit(code=1)

    definition_id: Optional[UUID] = None

    # --- Create or Update Definition ---
    try:
        if existing_definition:
            definition_id = existing_definition.id
            if not update:
                typer.secho(f"Error: Agent Definition '{agent_name}' already exists (ID: {definition_id}). Use --update to overwrite.", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)

            typer.echo(f"Updating existing Agent Definition (ID: {definition_id})...")
            # Create payload using existing definition fields as defaults
            definition_payload = AgentDefinitionCreate(
                name=agent_name,
                description=description or existing_definition.description, # Keep old desc if none provided
                definition=agent_code,
                definition_type='python', # Assuming python
                input_schema=input_schema or existing_definition.input_schema,
                output_schema=output_schema or existing_definition.output_schema,
                memory_template=memory_template or existing_definition.memory_template,
                environment_variables=env_variables or existing_definition.environment_variables,
            )
            # Call the client's update method
            updated_def = client.update_agent_definition(definition_id, definition_payload)
            typer.secho(f"Agent Definition '{updated_def.name}' updated (ID: {updated_def.id}).", fg=typer.colors.GREEN)

        else:
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

    except (MaestroValidationError, MaestroApiError) as e:
        typer.secho(f"API Error creating/updating definition: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
         typer.secho(f"Unexpected error during definition operation: {e}", fg=typer.colors.RED, err=True)
         raise typer.Exit(code=1)


    # --- Create or Update Agent (if requested) ---
    if create_agent_flag and definition_id:
        if not agent_type:
             typer.secho("Error: --agent-type is required when creating/updating an agent.", fg=typer.colors.RED, err=True)
             raise typer.Exit(code=1)

        # Check for existing agent with the same name
        try:
            typer.echo(f"Checking for existing agent named '{agent_name}'...")
            all_agents = client.list_agents() # TODO: Optimize if API supports filtering by name
            existing_agent = next((a for a in all_agents if a.name == agent_name), None)
        except MaestroApiError as e:
             typer.secho(f"API Error checking for agent: {e}", fg=typer.colors.RED, err=True)
             raise typer.Exit(code=1)

        agent_id: Optional[UUID] = None

        try:
            if existing_agent:
                agent_id = existing_agent.id
                if not update:
                     typer.secho(f"Error: Agent '{agent_name}' already exists (ID: {agent_id}). Use --update to modify.", fg=typer.colors.RED, err=True)
                   
                     return # Stop processing agent

                typer.echo(f"Updating existing Agent (ID: {agent_id}) to use definition {definition_id}...")
                # Prepare agent update data
                agent_update_data = AgentUpdate(
                    name=agent_name,
                    description=description or existing_agent.description,
                    agent_definition_id=definition_id,
                    agent_type=agent_type or existing_agent.agent_type,
                    capabilities=existing_agent.capabilities,
                    agent_metadata=existing_agent.agent_metadata
                )
                # Call the client's update method
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

        except (MaestroValidationError, MaestroApiError) as e:
            typer.secho(f"API Error creating/updating agent: {e}", fg=typer.colors.RED, err=True)
         
        except Exception as e:
            typer.secho(f"Unexpected error during agent operation: {e}", fg=typer.colors.RED, err=True)
            # raise typer.Exit(code=1)

    elif not create_agent_flag:
         typer.echo("Skipping agent creation/update (--create-agent not specified).")

    typer.echo("Deployment process finished.")

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

if __name__ == "__main__":
    app()

    