import typer
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from uuid import UUID
from datetime import datetime
from ..config import load_project_state, save_project_state
from ...maestro import MaestroClient
from ...maestro.models import AgentDefinitionCreate, AgentCreate, AgentUpdate, Agent, AgentDefinition
from ...maestro.exceptions import MaestroApiError

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
                import os
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
    typer.echo(f"  Project state saved to {project_dir / 'maestro_state.json'}")