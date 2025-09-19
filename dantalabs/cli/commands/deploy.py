import typer
from pathlib import Path
from typing import Optional, Annotated
from uuid import UUID
from datetime import datetime
from ..config import save_project_state, PROJECT_STATE_FILE
from ..utils.client import get_client
from ..utils.deployment import get_deploy_mode, deploy_single_file, deploy_bundle_with_state
from ..utils.schemas import load_schemas, load_env_variables

app = typer.Typer()

@app.command()
def deploy_command(
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
    # Client options
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