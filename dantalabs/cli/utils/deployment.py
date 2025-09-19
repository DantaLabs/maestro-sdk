import typer
import time
import json
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from uuid import UUID
from datetime import datetime
from ..config import load_project_state, save_project_state
from ...maestro import MaestroClient
from ...maestro.models import AgentDefinitionCreate, AgentCreate, AgentUpdate, Agent, AgentDefinition
from ...maestro.exceptions import MaestroApiError

def deploy_agent_unified(
    client: MaestroClient,
    bundle_path: Path,
    agent_name: str,
    description: Optional[str] = None,
    version: Optional[str] = "1.0.0",
    entrypoint: Optional[str] = "main.py",
    create_agent: bool = True,
    auto_deploy_service: bool = True,
    agent_type: str = "general",
    capabilities: Optional[list] = None,
    external_org_access: bool = False,
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    memory_template: Optional[Dict[str, Any]] = None,
    force_new_definition: bool = False,
    safe_mode: bool = False,
    replace_existing_agent: Optional[bool] = None,
    project_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Deploy an agent using the new unified deployment API endpoint.

    This function provides a clean interface to the consolidated deployment service
    that handles the complete pipeline from bundle upload to Knative deployment.

    Args:
        client: MaestroClient instance
        bundle_path: Path to ZIP bundle file
        agent_name: Name for the agent and agent definition
        description: Optional description
        version: Bundle version (default: "1.0.0")
        entrypoint: Python entrypoint file (default: "main.py")
        create_agent: Whether to create agent instance (default: True)
        auto_deploy_service: Whether to deploy to Knative (default: True)
        agent_type: Type of agent (default: "general")
        capabilities: List of agent capabilities
        external_org_access: Allow external access (default: False)
        input_schema: JSON schema for inputs
        output_schema: JSON schema for outputs
        memory_template: Memory configuration template
        force_new_definition: Force creation of a new agent definition even if one exists
        safe_mode: If True, do not overwrite an existing agent with the same name
        replace_existing_agent: Explicit control over replacing existing agents (defaults to not safe_mode)
        project_dir: Project directory for state tracking

    Returns:
        Dictionary with deployment results and status
    """

    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle file not found: {bundle_path}")

    if not bundle_path.suffix == '.zip':
        raise ValueError("Bundle file must be a ZIP archive")

    # Prepare deployment configuration
    deployment_config = {
        "name": agent_name,
        "description": description,
        "version": version,
        "entrypoint": entrypoint,
        "create_agent": create_agent,
        "force_new_definition": force_new_definition,
        "auto_deploy_service": auto_deploy_service,
        "agent_type": agent_type,
        "agent_description": description,  # Use same description for agent
        "capabilities": capabilities or [],
        "external_org_access": external_org_access,
        "input_schema": input_schema,
        "output_schema": output_schema,
        "memory_template": memory_template,
        "safe_mode": safe_mode,
        "replace_existing_agent": replace_existing_agent
    }

    if deployment_config.get("replace_existing_agent") is None:
        deployment_config["replace_existing_agent"] = not safe_mode

    # Remove None values to avoid issues
    deployment_config = {k: v for k, v in deployment_config.items() if v is not None}

    typer.echo(f"🚀 Starting deployment of '{agent_name}' using unified pipeline...")

    try:
        # Call the unified deployment endpoint (multipart form upload)
        with open(bundle_path, "rb") as bundle_file:
            files = {
                "bundle": (bundle_path.name, bundle_file, "application/zip"),
                "deployment_data": (None, json.dumps(deployment_config), "application/json"),
            }

            result = client.http.request(
                "POST",
                "/api/v1/agents/deploy",
                files=files,
                organization_id=client.organization_id,
                custom_timeout=600.0,
            )

        # Display results
        typer.secho("✅ Deployment completed successfully!", fg=typer.colors.GREEN)

        # Agent Definition info
        if result.get("agent_definition_created"):
            typer.echo(f"📄 Created new Agent Definition: {result['agent_definition_id']}")
        else:
            typer.echo(f"📄 Updated existing Agent Definition: {result['agent_definition_id']}")

        # Container build info
        if result.get("docker_image_url"):
            if result.get("dockerfile_detected"):
                typer.echo(f"🐳 Built container image using custom Dockerfile")
            else:
                typer.echo(f"🐳 Built container image using standard Python template")

            if result.get("build_duration_seconds"):
                typer.echo(f"⏱️  Build completed in {result['build_duration_seconds']:.1f} seconds")

        # Agent info
        if result.get("agent_created"):
            typer.echo(f"🤖 Created new Agent: {result['agent_id']}")
        elif result.get("agent_id"):
            typer.echo(f"🤖 Updated existing Agent: {result['agent_id']}")

        # Service deployment info
        if result.get("service_deployed"):
            typer.secho(f"🌐 Service deployed successfully: {result['service_url']}", fg=typer.colors.CYAN)
            typer.echo(f"📦 Service available at: {result['service_url']}")

        # Show any messages
        if result.get("messages"):
            typer.echo("\n📋 Deployment log:")
            for message in result["messages"]:
                typer.echo(f"   • {message}")

        # Save deployment state
        if project_dir and result.get("agent_definition_id"):
            state_data = {
                "agent_name": agent_name,
                "agent_definition_id": str(result["agent_definition_id"]),
                "agent_id": str(result["agent_id"]) if result.get("agent_id") else None,
                "docker_image_url": result.get("docker_image_url"),
                "service_url": result.get("service_url"),
                "last_deploy_mode": "unified",
                "last_deployed_at": datetime.now().isoformat(),
                "deployment_status": result.get("deployment_status")
            }
            save_project_state(state_data, project_dir)
            typer.echo(f"💾 Saved deployment state to {project_dir / 'maestro_state.json'}")

        return result

    except Exception as e:
        # Filter out internal details from user-facing error messages
        error_msg = str(e)
        if any(keyword in error_msg.lower() for keyword in ["google cloud", "gcp", "knative", "kubernetes", "docker"]):
            typer.secho(f"❌ Deployment failed: Unable to deploy your agent. Please check your configuration and try again.", fg=typer.colors.RED)
        else:
            typer.secho(f"❌ Deployment failed: {error_msg}", fg=typer.colors.RED)
        raise


def check_deployment_status(
    client: MaestroClient,
    agent_definition_id: str
) -> Dict[str, Any]:
    """
    Check the deployment status of an agent definition.

    Args:
        client: MaestroClient instance
        agent_definition_id: Agent definition UUID

    Returns:
        Dictionary with deployment status information
    """
    try:
        response = client._client.get(f"/agents/definitions/{agent_definition_id}/deployment-status")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        error_msg = str(e)
        if any(keyword in error_msg.lower() for keyword in ["google cloud", "gcp", "knative", "kubernetes"]):
            typer.secho(f"❌ Failed to check deployment status: Unable to check status. Please try again later.", fg=typer.colors.RED)
        else:
            typer.secho(f"❌ Failed to check deployment status: {error_msg}", fg=typer.colors.RED)
        raise


def rebuild_agent_image(
    client: MaestroClient,
    agent_definition_id: str,
    bundle_path: Path,
    version: Optional[str] = None
) -> Dict[str, Any]:
    """
    Rebuild Docker image for an existing agent definition.

    Args:
        client: MaestroClient instance
        agent_definition_id: Existing agent definition UUID
        bundle_path: Path to updated ZIP bundle
        version: Optional new version number

    Returns:
        Dictionary with rebuild results
    """
    if not bundle_path.exists():
        raise FileNotFoundError(f"Bundle file not found: {bundle_path}")

    if not bundle_path.suffix == '.zip':
        raise ValueError("Bundle file must be a ZIP archive")

    typer.echo(f"🔄 Rebuilding Docker image for agent definition {agent_definition_id}...")

    try:
        with open(bundle_path, 'rb') as bundle_file:
            files = {"bundle": (bundle_path.name, bundle_file, "application/zip")}
            data = {}
            if version:
                data["version"] = version

            response = client._client.post(
                f"/agents/definitions/{agent_definition_id}/rebuild",
                files=files,
                data=data
            )
            response.raise_for_status()

            result = response.json()

        typer.secho("✅ Image rebuild completed successfully!", fg=typer.colors.GREEN)

        if result.get("docker_image_url"):
            typer.echo(f"🐳 Container image rebuilt successfully")

        if result.get("build_duration_seconds"):
            typer.echo(f"⏱️  Build completed in {result['build_duration_seconds']:.1f} seconds")

        return result

    except Exception as e:
        error_msg = str(e)
        if any(keyword in error_msg.lower() for keyword in ["google cloud", "gcp", "docker", "image"]):
            typer.secho(f"❌ Image rebuild failed: Unable to rebuild container image. Please check your bundle and try again.", fg=typer.colors.RED)
        else:
            typer.secho(f"❌ Image rebuild failed: {error_msg}", fg=typer.colors.RED)
        raise


def get_bundle_info(
    client: MaestroClient,
    agent_definition_id: str
) -> Dict[str, Any]:
    """
    Get detailed information about an agent definition's bundle.

    Args:
        client: MaestroClient instance
        agent_definition_id: Agent definition UUID

    Returns:
        Dictionary with bundle information
    """
    try:
        response = client._client.get(f"/agents/definitions/{agent_definition_id}/bundle-info")
        response.raise_for_status()
        return response.json()
    except Exception as e:
        error_msg = str(e)
        if any(keyword in error_msg.lower() for keyword in ["google cloud", "gcp", "storage"]):
            typer.secho(f"❌ Failed to get bundle info: Unable to retrieve bundle information. Please try again later.", fg=typer.colors.RED)
        else:
            typer.secho(f"❌ Failed to get bundle info: {error_msg}", fg=typer.colors.RED)
        raise


# Legacy function - kept for backward compatibility but marked as deprecated
def get_deploy_mode(client: MaestroClient, agent_name: str, project_dir: Optional[Path] = None) -> Tuple[str, Optional[Dict[str, Any]]]:
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

def deploy_single_file(
    client: MaestroClient,
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
    client: MaestroClient,
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
    from .schemas import load_schemas, load_env_variables
    
    # Load schemas and environment variables for bundle
    input_schema, output_schema, memory_template = load_schemas(source_dir, schema_file)
    env_variables = load_env_variables(source_dir, env_file)
    
    definition_id = None
    agent_id = None
    
    if deploy_mode == "create":
        # Create new bundle as container image
        typer.echo("Creating and deploying new bundle as container image...")
        agent_definition = client.create_and_upload_bundle_as_image(
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

        # For image-based deployments, create a new agent definition
        # since updating existing definitions with new images is complex
        typer.echo(f"Creating new image-based bundle definition to replace (ID: {definition_id})...")

        # Create new bundle as container image
        agent_definition = client.create_and_upload_bundle_as_image(
            source_dir=str(source_dir),
            name=agent_name + f"-updated-{int(time.time())}",  # Add timestamp to avoid conflicts
            description=description or existing_definition.description,
            input_schema=input_schema if input_schema else existing_definition.input_schema,
            output_schema=output_schema if output_schema else existing_definition.output_schema,
            shareable=False
        )

        # Update the definition_id to the new one
        definition_id = agent_definition.id
        typer.secho(f"New Agent Definition '{agent_definition.name}' created (ID: {definition_id}).", fg=typer.colors.GREEN)
        typer.echo("Note: Created new definition due to image-based deployment approach")
    
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
    typer.echo(f"  Project state saved to {project_dir / 'maestro_state.json'}")
