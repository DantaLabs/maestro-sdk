import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Annotated, Iterator
from uuid import UUID

import typer

from ..utils.client import get_client
from ..utils.deployment import deploy_agent_unified
from ..utils.schemas import load_schemas

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
    version: Annotated[str, typer.Option(
        "--version",
        help="Semantic version for the deployed bundle.",
    )] = "1.0.0",
    entrypoint: Annotated[Optional[str], typer.Option(
        "--entrypoint",
        help="Entrypoint Python file inside the bundle (defaults to backend auto-detection).",
    )] = None,
    as_service: Annotated[bool, typer.Option(
        "--service/--no-service",
        help="Deploy as a long-running service once the agent is created."
    )] = True,
    create_agent: Annotated[bool, typer.Option(
        "--create-agent/--definition-only",
        help="Create/update an Agent instance linked to the definition (default: True).",
    )] = True,
    force_new_definition: Annotated[bool, typer.Option(
        "--force-definition/--reuse-definition",
        help="Force creation of a brand new agent definition instead of reusing by name."
    )] = False,
    safe: Annotated[bool, typer.Option(
        "--safe/--overwrite",
        help="Prevent overwriting an existing agent with the same name.",
    )] = False,
    schema_file: Annotated[Optional[Path], typer.Option(
        "--schema-file", 
        help="Path to a JSON file containing input/output/memory schemas. Auto-detected if not specified."
    )] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Package the selected source, upload it, and let the unified deployment pipeline handle it."""
    client = get_client(org_id, url, token)

    if file_path is None:
        file_path = Path.cwd()

    if not file_path.exists():
        typer.secho(f"Error: Path '{file_path}' does not exist.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    project_dir = file_path if file_path.is_dir() else file_path.parent

    if file_path.is_file() and file_path.suffix != ".py":
        typer.secho("Error: When providing a file it must be a Python module (.py).", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    agent_name = name or (file_path.name if file_path.is_dir() else file_path.stem)

    typer.echo(f"Packaging '{agent_name}' for deployment...")

    # Load schemas so they can be attached to the deployment request
    schema_base = file_path if file_path.is_dir() else file_path.parent
    input_schema, output_schema, memory_template = load_schemas(schema_base, schema_file)

    with _temporary_bundle(file_path) as bundle_path:
        deploy_agent_unified(
            client=client,
            bundle_path=bundle_path,
            agent_name=agent_name,
            description=description,
            version=version,
            entrypoint=entrypoint,
            create_agent=create_agent,
            auto_deploy_service=as_service,
            agent_type=agent_type,
            capabilities=None,
            external_org_access=False,
            input_schema=input_schema,
            output_schema=output_schema,
            memory_template=memory_template,
            force_new_definition=force_new_definition,
            safe_mode=safe,
            project_dir=project_dir
        )


@contextmanager
def _temporary_bundle(source: Path) -> Iterator[Path]:
    """Create a temporary ZIP archive for the provided source path."""
    temp_file = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    temp_file.close()
    archive_path = Path(temp_file.name)

    try:
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            if source.is_dir():
                for path in source.rglob("*"):
                    if path.is_file():
                        arcname = path.relative_to(source)
                        zip_file.write(path, arcname)
            else:
                zip_file.write(source, source.name)

        yield archive_path
    finally:
        try:
            archive_path.unlink(missing_ok=True)
        except Exception:
            pass
