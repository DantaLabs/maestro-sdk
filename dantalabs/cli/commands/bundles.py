import typer
from typing import Optional, Annotated
from uuid import UUID
from pathlib import Path
from ..utils.client import get_client
from ...maestro.exceptions import MaestroApiError, MaestroValidationError

app = typer.Typer()

@app.command("create-bundle")
def create_bundle_command(
    source_dir: Annotated[Optional[Path], typer.Argument(
        help="Path to the directory containing agent code. If not provided, uses current directory."
    )] = None,
    output_path: Annotated[Optional[Path], typer.Option(
        "--output", "-o", help="Path for the output ZIP file. If not provided, creates in temp directory."
    )] = None,
    include_requirements: Annotated[bool, typer.Option(
        "--include-requirements/--no-requirements",
        help="Include requirements from pyproject.toml or requirements.txt (default: True)."
    )] = True,
    install_dependencies: Annotated[bool, typer.Option(
        "--install-deps/--no-install-deps", 
        help="Install dependencies into the bundle (default: True)."
    )] = True,
):
    """Creates a ZIP bundle from a source directory for agent deployment."""
    from ...maestro.bundles.creator import BundleCreator
    
    # Use current directory if no source_dir provided
    if source_dir is None:
        source_dir = Path.cwd()
    
    # Validate source directory exists
    if not source_dir.exists() or not source_dir.is_dir():
        typer.secho(f"Error: Source directory '{source_dir}' does not exist or is not a directory.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    try:
        typer.echo(f"Creating bundle from '{source_dir}'...")
        
        bundle_creator = BundleCreator()
        bundle_path = bundle_creator.create_bundle(
            source_dir=str(source_dir),
            output_path=str(output_path) if output_path else None,
            include_requirements=include_requirements,
            install_dependencies=install_dependencies
        )
        
        typer.secho(f"Bundle created successfully: {bundle_path}", fg=typer.colors.GREEN)
        typer.echo(f"Bundle size: {Path(bundle_path).stat().st_size / 1024 / 1024:.2f} MB")
        
    except Exception as e:
        typer.secho(f"Error creating bundle: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("upload-bundle")
def upload_bundle_command(
    bundle_path: Annotated[Path, typer.Argument(help="Path to the ZIP bundle file to upload")],
    name: Annotated[str, typer.Option("--name", "-n", help="Name for the Agent Definition")],
    description: Annotated[Optional[str], typer.Option(
        "--desc", "-d", help="Optional description for the Agent Definition"
    )] = None,
    shareable: Annotated[bool, typer.Option(
        "--shareable/--private", help="Whether the agent definition is shareable (default: False)"
    )] = False,
    entrypoint: Annotated[str, typer.Option(
        "--entrypoint", "-e", help="Main entry point file for the bundle (default: main.py)"
    )] = "main.py",
    version: Annotated[str, typer.Option(
        "--version", "-v", help="Version of the bundle (default: 1.0.0)"
    )] = "1.0.0",
    upload_timeout: Annotated[float, typer.Option(
        "--timeout", help="Upload timeout in seconds (default: 600)"
    )] = 600.0,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Uploads a ZIP bundle to create a new Agent Definition."""
    client = get_client(org_id, url, token)
    
    # Validate bundle path
    if not bundle_path.exists() or not bundle_path.is_file():
        typer.secho(f"Error: Bundle file '{bundle_path}' does not exist or is not a file.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    if not bundle_path.name.lower().endswith('.zip'):
        typer.secho("Error: Bundle file must be a ZIP file.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    try:
        typer.echo(f"Uploading bundle '{bundle_path}' as '{name}'...")
        
        agent_definition = client.upload_agent_bundle(
            bundle_path=str(bundle_path),
            name=name,
            description=description,
            shareable=shareable,
            entrypoint=entrypoint,
            version=version,
            upload_timeout=upload_timeout
        )
        
        typer.secho(f"Agent Definition '{agent_definition.name}' created successfully (ID: {agent_definition.id}).", fg=typer.colors.GREEN)
        
    except MaestroApiError as e:
        typer.secho(f"API Error uploading bundle: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("deploy-bundle") 
def deploy_bundle_command(
    name: Annotated[str, typer.Option("--name", "-n", help="Name for the Agent Definition")],
    source_dir: Annotated[Optional[Path], typer.Argument(
        help="Path to the directory containing agent code. If not provided, uses current directory."
    )] = None,
    description: Annotated[Optional[str], typer.Option(
        "--desc", "-d", help="Optional description for the Agent Definition"
    )] = None,
    create_agent: Annotated[bool, typer.Option(
        "--create-agent/--definition-only", 
        help="Create an Agent instance linked to the definition (default: True)"
    )] = True,
    agent_type: Annotated[str, typer.Option(
        "--agent-type", "-t", help="Type of the agent (e.g., 'script', 'chat', 'tool') (default: script)"
    )] = "script",
    shareable: Annotated[bool, typer.Option(
        "--shareable/--private", help="Whether the agent definition is shareable (default: False)"
    )] = False,
    include_requirements: Annotated[bool, typer.Option(
        "--include-requirements/--no-requirements", 
        help="Include requirements automatically (default: True)"
    )] = True,
    install_dependencies: Annotated[bool, typer.Option(
        "--install-deps/--no-install-deps", 
        help="Install dependencies into bundle (default: True)"
    )] = True,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Creates a bundle from source directory and deploys it as an Agent Definition (and optionally Agent)."""
    client = get_client(org_id, url, token)
    
    # Use current directory if no source_dir provided
    if source_dir is None:
        source_dir = Path.cwd()
    
    # Validate source directory exists
    if not source_dir.exists() or not source_dir.is_dir():
        typer.secho(f"Error: Source directory '{source_dir}' does not exist or is not a directory.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    try:
        typer.echo(f"Creating and deploying bundle from '{source_dir}' as '{name}'...")
        
        agent_definition = client.create_and_upload_bundle(
            source_dir=str(source_dir),
            name=name,
            description=description,
            shareable=shareable,
            include_requirements=include_requirements,
            install_dependencies=install_dependencies,
            cleanup_bundle=True
        )
        
        typer.secho(f"Agent Definition '{agent_definition.name}' created successfully (ID: {agent_definition.id}).", fg=typer.colors.GREEN)
        
        # Optionally create agent instance
        if create_agent:
            from ...maestro.models import AgentCreate
            typer.echo(f"Creating agent instance...")
            
            agent_payload = AgentCreate(
                name=name,
                description=description,
                agent_type=agent_type,
                agent_definition_id=agent_definition.id,
            )
            
            created_agent = client.create_agent(agent_payload)
            typer.secho(f"Agent '{created_agent.name}' created successfully (ID: {created_agent.id}).", fg=typer.colors.GREEN)
        
    except (MaestroApiError, MaestroValidationError) as e:
        typer.secho(f"Error deploying bundle: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("update-bundle")
def update_bundle_command(
    definition_id: Annotated[UUID, typer.Argument(help="Agent Definition ID to update")],
    bundle_path: Annotated[Path, typer.Argument(help="Path to the new ZIP bundle file")],
    entrypoint: Annotated[Optional[str], typer.Option(
        "--entrypoint", "-e", help="Main entry point file for the bundle"
    )] = None,
    version: Annotated[Optional[str], typer.Option(
        "--version", "-v", help="Version of the bundle"
    )] = None,
    upload_timeout: Annotated[float, typer.Option(
        "--timeout", help="Upload timeout in seconds (default: 600)"
    )] = 600.0,
    # Client options  
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Updates an existing bundled Agent Definition with a new ZIP bundle."""
    client = get_client(org_id, url, token)
    
    # Validate bundle path
    if not bundle_path.exists() or not bundle_path.is_file():
        typer.secho(f"Error: Bundle file '{bundle_path}' does not exist or is not a file.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    if not bundle_path.name.lower().endswith('.zip'):
        typer.secho("Error: Bundle file must be a ZIP file.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    
    try:
        typer.echo(f"Updating Agent Definition {definition_id} with new bundle '{bundle_path}'...")
        
        updated_definition = client.update_agent_bundle(
            definition_id=definition_id,
            bundle_path=str(bundle_path),
            entrypoint=entrypoint,
            version=version,
            upload_timeout=upload_timeout
        )
        
        typer.secho(f"Agent Definition '{updated_definition.name}' updated successfully (ID: {updated_definition.id}).", fg=typer.colors.GREEN)
        
    except MaestroApiError as e:
        typer.secho(f"API Error updating bundle: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("download-definition-bundle")
def download_definition_bundle_command(
    definition_id: Annotated[UUID, typer.Argument(help="Agent Definition ID to download bundle from")],
    output_path: Annotated[Optional[Path], typer.Option(
        "--output", "-o", help="Path to save the downloaded bundle. If not provided, saves in current directory."
    )] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Downloads the bundle for a specific agent definition."""
    client = get_client(org_id, url, token)
    
    # Determine output path
    if output_path is None:
        output_path = Path.cwd() / f"agent_definition_{definition_id}.zip"
    
    try:
        typer.echo(f"Downloading bundle for Agent Definition {definition_id}...")
        
        bundle_content = client.download_agent_definition_bundle(definition_id)
        
        # Write bundle to file
        with open(output_path, 'wb') as f:
            f.write(bundle_content)
        
        typer.secho(f"Bundle downloaded successfully: {output_path}", fg=typer.colors.GREEN)
        typer.echo(f"Bundle size: {len(bundle_content) / 1024 / 1024:.2f} MB")
        
    except MaestroApiError as e:
        typer.secho(f"API Error downloading bundle: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)