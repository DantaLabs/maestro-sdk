import typer
from typing import Optional, Annotated, List
from uuid import UUID
from pathlib import Path
from ..utils.client import get_client
from ..config import load_config
from ...maestro.exceptions import MaestroApiError, MaestroValidationError

app = typer.Typer()

@app.command("deploy")
def deploy_service_command(
    agent_id: Annotated[Optional[str], typer.Argument(help="Agent ID to deploy as a Knative service")] = None,
    executor_type: Annotated[Optional[str], typer.Option(
        "--executor", help="Executor type for deployment (e.g., 'kubernetes')"
    )] = None,
    env_file: Annotated[Optional[Path], typer.Option(
        "--env-file", help="Path to a .env file containing environment variables for the service"
    )] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Deploy an agent as a Knative service for auto-scaling."""
    client = get_client(org_id, url, token)

    # Resolve agent_id
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
        typer.secho("Error: No agent ID provided or set. Use agent_id argument or 'dlm use-agent' first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Load environment variables from .env file if provided
    env_vars = None
    if not env_file:
        default_env_file = Path('.env')
        if default_env_file.exists():
            env_file = default_env_file
            typer.echo(f"Found default .env file in current directory.")

    if env_file and env_file.exists():
        try:
            import dotenv
            typer.echo(f"Loading environment variables from '{env_file}'...")
            env_vars = dotenv.dotenv_values(env_file)
            if env_vars:
                typer.echo(f"Loaded {len(env_vars)} environment variables.")
        except Exception as e:
            typer.secho(f"Error reading .env file '{env_file}': {e}", fg=typer.colors.YELLOW, err=True)

    # Deploy the service
    try:
        typer.echo(f"Deploying agent {agent_id_to_use} to Knative service...")
        deployment_response = client.deploy_service(agent_id_to_use, executor_type, env_vars)

        typer.secho("Agent deployed to Knative successfully!", fg=typer.colors.GREEN)
        typer.echo(f"  Service URL: {deployment_response.get('service_url', 'N/A')}")
        typer.echo(f"  Service Name: {deployment_response.get('service_name', 'N/A')}")
        typer.echo(f"  Status: {deployment_response.get('deployment_status', 'N/A')}")

        # Show monitoring commands
        typer.echo(f"\n📊 Monitor your deployment:")
        typer.echo(f"  dlm service deployment-status {agent_id_to_use}")
        typer.echo(f"  dlm service logs {agent_id_to_use}")
        typer.echo(f"\n💡 Your service will automatically scale based on traffic!")

    except MaestroApiError as e:
        error_msg = str(e)
        # Remove internal technical details from user-facing errors
        if any(keyword in error_msg.lower() for keyword in ["cloud run", "knative", "kubernetes", "gcp", "google cloud"]):
            typer.secho(f"Deployment failed: Unable to deploy your service. Please check your configuration and try again.", fg=typer.colors.RED, err=True)
        else:
            typer.secho(f"Deployment failed: {error_msg}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("deployment-status")
def get_deployment_status_command(
    agent_id: Annotated[Optional[str], typer.Argument(help="Agent ID to get deployment status for")] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Get the deployment status of an agent service in Knative."""
    client = get_client(org_id, url, token)

    # Resolve agent_id
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
        typer.secho("Error: No agent ID provided or set. Use agent_id argument or 'dlm use-agent' first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Get deployment status
    try:
        status = client.get_deployment_status(agent_id_to_use)

        typer.echo(f"Deployment Status for Agent {agent_id_to_use}:")

        deployment_status = status.get('deployment_status', 'unknown')
        if deployment_status == 'deployed':
            typer.secho(f"  Status: {deployment_status}", fg=typer.colors.GREEN)
        else:
            typer.secho(f"  Status: {deployment_status}", fg=typer.colors.RED)

        typer.echo(f"  Service Ready: {status.get('service_ready', False)}")
        typer.echo(f"  Service URL: {status.get('service_url', 'N/A')}")
        typer.echo(f"  Current Scale: {status.get('current_scale', 0)} replicas")
        typer.echo(f"  Service Name: {status.get('service_name', 'N/A')}")

        if status.get('deployed_at'):
            typer.echo(f"  Deployed At: {status.get('deployed_at')}")

        # Show conditions if available
        conditions = status.get('conditions', [])
        if conditions:
            typer.echo(f"\n  Conditions:")
            for condition in conditions:
                cond_type = condition.get('type', 'Unknown')
                cond_status = condition.get('status', 'Unknown')
                cond_reason = condition.get('reason', '')
                color = typer.colors.GREEN if cond_status == 'True' else typer.colors.RED
                typer.secho(f"    {cond_type}: {cond_status}", fg=color)
                if cond_reason:
                    typer.echo(f"      Reason: {cond_reason}")

    except MaestroApiError as e:
        if "404" in str(e):
            typer.secho(f"Agent {agent_id_to_use} is not deployed as a service", fg=typer.colors.YELLOW)
            typer.echo("Deploy it first with:")
            typer.echo(f"  dlm service deploy {agent_id_to_use}")
        else:
            typer.secho(f"API Error getting deployment status: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

@app.command("start")
def start_service_command(
    agent_id: Annotated[Optional[str], typer.Argument(help="Agent ID to start as a service")] = None,
    env_file: Annotated[Optional[Path], typer.Option(
        "--env-file", help="Path to a .env file containing environment variables for the service"
    )] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """[DEPRECATED] Start a long-running agent service. Use 'deploy' for modern agents."""
    typer.secho("Warning: 'dlm service start' is deprecated!", fg=typer.colors.YELLOW, err=True)
    typer.echo("For modern agents, use: dlm service deploy <agent_id>")
    typer.echo("This command will route to the legacy start endpoint.")
    typer.echo()

    client = get_client(org_id, url, token)

    # Resolve agent_id
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
        typer.secho("Error: No agent ID provided or set. Use agent_id argument or 'dlm use-agent' first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Load environment variables from .env file if provided
    env_vars = None
    if not env_file:
        default_env_file = Path('.env')
        if default_env_file.exists():
            env_file = default_env_file
            typer.echo(f"Found default .env file in current directory.")

    if env_file and env_file.exists():
        try:
            import dotenv
            typer.echo(f"Loading environment variables from '{env_file}'...")
            env_vars = dotenv.dotenv_values(env_file)
            if env_vars:
                typer.echo(f"Loaded {len(env_vars)} environment variables.")
        except Exception as e:
            typer.secho(f"Error reading .env file '{env_file}': {e}", fg=typer.colors.YELLOW, err=True)

    # Start the service
    try:
        typer.echo(f"Starting agent service for agent {agent_id_to_use}...")
        service_response = client.start_service(agent_id_to_use, env_vars=env_vars)

        typer.secho("Agent service started successfully!", fg=typer.colors.GREEN)
        typer.echo(f"  Service URL: {service_response.get('endpoint_url', 'N/A')}")
        typer.echo(f"  Instance ID: {service_response.get('instance_id', 'N/A')}")
        typer.echo(f"  Status: {service_response.get('status', 'N/A')}")

        # Show monitoring commands
        typer.echo(f"\n📊 Monitor your service:")
        typer.echo(f"  dlm service status {agent_id_to_use}")
        typer.echo(f"  dlm service logs {agent_id_to_use}")

    except MaestroApiError as e:
        typer.secho(f"API Error starting service: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("stop")
def stop_service_command(
    agent_id: Annotated[Optional[str], typer.Argument(help="Agent ID to stop service for")] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Stop a running agent service."""
    client = get_client(org_id, url, token)

    # Resolve agent_id
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
        typer.secho("Error: No agent ID provided or set. Use agent_id argument or 'dlm use-agent' first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Stop the service
    try:
        typer.echo(f"Stopping agent service for agent {agent_id_to_use}...")
        client.stop_service(agent_id_to_use)
        typer.secho("Agent service stopped successfully!", fg=typer.colors.GREEN)

    except MaestroApiError as e:
        typer.secho(f"API Error stopping service: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("status")
def get_service_status_command(
    agent_id: Annotated[Optional[str], typer.Argument(help="Agent ID to get status for")] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """[DEPRECATED] Get the status of a running agent service. Use 'deployment-status' for modern agents."""
    typer.secho("Warning: 'dlm service status' is deprecated!", fg=typer.colors.YELLOW, err=True)
    typer.echo("For modern agents, use: dlm service deployment-status <agent_id>")
    typer.echo("This command will check legacy instance status.")
    typer.echo()
    client = get_client(org_id, url, token)

    # Resolve agent_id
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
        typer.secho("Error: No agent ID provided or set. Use agent_id argument or 'dlm use-agent' first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Get service status
    try:
        status = client.get_service_status(agent_id_to_use)

        typer.echo(f"Service Status for Agent {agent_id_to_use}:")
        typer.echo(f"  Service URL: {status.get('endpoint_url', 'N/A')}")
        typer.echo(f"  Instance ID: {status.get('instance_id', 'N/A')}")
        typer.echo(f"  Status: {status.get('status', 'N/A')}")
        typer.echo(f"  Created: {status.get('created_at', 'N/A')}")

        if status.get('last_health_check'):
            typer.echo(f"  Last Health Check: {status.get('last_health_check')}")

    except MaestroApiError as e:
        if "404" in str(e):
            typer.secho(f"No running service found for agent {agent_id_to_use}", fg=typer.colors.YELLOW)
        else:
            typer.secho(f"API Error getting service status: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

@app.command("list")
def list_services_command(
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """List all running agent services for the organization."""
    client = get_client(org_id, url, token)

    try:
        services = client.list_services()

        if not services:
            typer.echo("No running agent services found.")
            return

        typer.echo(f"Found {len(services)} running service(s):")
        typer.echo()

        for service in services:
            typer.echo(f"• Agent ID: {service.get('agent_id', 'N/A')}")
            typer.echo(f"  Service URL: {service.get('endpoint_url', 'N/A')}")
            typer.echo(f"  Instance ID: {service.get('instance_id', 'N/A')}")
            typer.echo(f"  Status: {service.get('status', 'N/A')}")
            typer.echo(f"  Created: {service.get('created_at', 'N/A')}")
            typer.echo()

    except MaestroApiError as e:
        typer.secho(f"API Error listing services: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("logs")
def get_service_logs_command(
    agent_id: Annotated[Optional[str], typer.Argument(help="Agent ID to get logs for")] = None,
    limit: Annotated[int, typer.Option("--limit", "-l", help="Maximum number of log entries to return")] = 100,
    offset: Annotated[int, typer.Option("--offset", "-o", help="Number of entries to skip for pagination")] = 0,
    log_level: Annotated[Optional[str], typer.Option("--level", help="Filter by log level (error, warning, info, debug)")] = None,
    instance_id: Annotated[Optional[str], typer.Option("--instance", help="Specific instance ID to get logs for")] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Get logs for a specific agent service."""
    client = get_client(org_id, url, token)

    # Resolve agent_id
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
        typer.secho("Error: No agent ID provided or set. Use agent_id argument or 'dlm use-agent' first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Get service logs
    try:
        logs = client.get_service_logs(
            agent_id_to_use,
            instance_id=instance_id,
            limit=limit,
            offset=offset,
            log_level=log_level
        )

        if not logs:
            typer.echo("No logs found for this service.")
            return

        typer.echo(f"Service Logs for Agent {agent_id_to_use} (showing {len(logs)} entries):")
        typer.echo()

        for log_entry in logs:
            timestamp = log_entry.get('timestamp', 'N/A')
            level = log_entry.get('level', 'INFO')
            message = log_entry.get('message', '')
            source = log_entry.get('source', 'unknown')

            # Color code based on log level
            level_color = typer.colors.WHITE
            if level.upper() == 'ERROR':
                level_color = typer.colors.RED
            elif level.upper() == 'WARNING':
                level_color = typer.colors.YELLOW
            elif level.upper() == 'DEBUG':
                level_color = typer.colors.BLUE

            typer.secho(f"[{timestamp}] {level.upper()}", fg=level_color, nl=False)
            typer.echo(f" [{source}] {message}")

    except MaestroApiError as e:
        typer.secho(f"API Error getting service logs: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("execute")
def execute_via_service_command(
    input_json: Annotated[Optional[str], typer.Argument(help="JSON string of input variables or path to JSON file")] = None,
    agent_id: Annotated[Optional[str], typer.Option("--agent-id", "-a", help="Agent ID to execute via service")] = None,
    function_name: Annotated[Optional[str], typer.Option("--function", "-f", help="Function name to call in the agent")] = None,
    input_file: Annotated[Optional[Path], typer.Option("--file", help="Path to JSON file containing input variables")] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Execute a request via a running agent service."""
    import json

    client = get_client(org_id, url, token)

    # Handle input variables (same logic as run_agent_command)
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

    # Resolve agent_id
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

    # Execute via service
    try:
        typer.echo(f"Executing via agent service {agent_id_to_use}...")
        result = client.execute_via_service(
            agent_id_to_use,
            input_variables,
            function_name=function_name
        )

        typer.secho("Execution via service completed successfully!", fg=typer.colors.GREEN)
        typer.echo(json.dumps(result, indent=2))

    except MaestroApiError as e:
        typer.secho(f"API Error executing via service: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("health")
def get_service_health_command(
    agent_id: Annotated[Optional[str], typer.Argument(help="Agent ID to check health for")] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Get health information for an agent service."""
    client = get_client(org_id, url, token)

    # Resolve agent_id
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
        typer.secho("Error: No agent ID provided or set. Use agent_id argument or 'dlm use-agent' first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Get service health
    try:
        health = client.get_service_health(agent_id_to_use)

        typer.echo(f"Service Health for Agent {agent_id_to_use}:")

        # Show basic health status
        status = health.get('status', 'unknown')
        if status == 'healthy':
            typer.secho(f"  Status: {status}", fg=typer.colors.GREEN)
        elif status == 'unhealthy':
            typer.secho(f"  Status: {status}", fg=typer.colors.RED)
        else:
            typer.secho(f"  Status: {status}", fg=typer.colors.YELLOW)

        # Show additional health details
        if health.get('uptime'):
            typer.echo(f"  Uptime: {health.get('uptime')}")
        if health.get('memory_usage'):
            typer.echo(f"  Memory: {health.get('memory_usage')}")
        if health.get('cpu_usage'):
            typer.echo(f"  CPU: {health.get('cpu_usage')}")
        if health.get('last_request'):
            typer.echo(f"  Last Request: {health.get('last_request')}")

    except MaestroApiError as e:
        typer.secho(f"API Error getting service health: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("metrics")
def get_service_metrics_command(
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Get metrics about all running agent services in the organization."""
    client = get_client(org_id, url, token)

    try:
        metrics = client.get_service_metrics()

        typer.echo("Agent Service Metrics:")
        typer.echo(f"  Total Services: {metrics.get('total_services', 0)}")
        typer.echo(f"  Running Services: {metrics.get('running_services', 0)}")
        typer.echo(f"  Healthy Services: {metrics.get('healthy_services', 0)}")
        typer.echo(f"  Unhealthy Services: {metrics.get('unhealthy_services', 0)}")

        if metrics.get('resource_usage'):
            usage = metrics['resource_usage']
            typer.echo(f"  Total Memory: {usage.get('total_memory', 'N/A')}")
            typer.echo(f"  Total CPU: {usage.get('total_cpu', 'N/A')}")

        if metrics.get('request_stats'):
            stats = metrics['request_stats']
            typer.echo(f"  Total Requests: {stats.get('total_requests', 0)}")
            typer.echo(f"  Requests/min: {stats.get('requests_per_minute', 0)}")

    except MaestroApiError as e:
        typer.secho(f"API Error getting service metrics: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("proxy")
def proxy_request_command(
    agent_id: Annotated[Optional[str], typer.Argument(help="Agent ID to send request to")] = None,
    path: Annotated[str, typer.Argument(help="Path to request (e.g., '/', '/health')")] = "/",
    method: Annotated[str, typer.Option("--method", "-m", help="HTTP method")] = "GET",
    data: Annotated[Optional[str], typer.Option("--data", "-d", help="Request body as JSON string")] = None,
    header: Annotated[List[str], typer.Option("--header", "-H", help="Headers in format 'Key: Value'")] = [],
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Send HTTP requests to deployed agent services via proxy."""
    import json
    import httpx

    client = get_client(org_id, url, token)

    # Resolve agent_id
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
        typer.secho("Error: No agent ID provided or set. Use agent_id argument or 'dlm use-agent' first.", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # Parse headers
    headers = {}
    for header_str in header:
        if ':' in header_str:
            key, value = header_str.split(':', 1)
            headers[key.strip()] = value.strip()

    # Parse data
    request_data = None
    if data:
        try:
            request_data = json.loads(data)
        except json.JSONDecodeError:
            # If not JSON, send as text
            request_data = data

    # Build proxy URL
    base_url = client.http.base_url.rstrip('/')
    proxy_url = f"{base_url}/api/v1/agent-services/{agent_id_to_use}/service/proxy{path}"

    # Make request
    try:
        typer.echo(f"Making {method} request to {proxy_url}")

        with httpx.Client(timeout=60.0) as http_client:
            auth_headers = {"Authorization": f"Bearer {client.http._token}"}
            auth_headers.update(headers)

            response = http_client.request(
                method=method,
                url=proxy_url,
                headers=auth_headers,
                json=request_data if isinstance(request_data, dict) else None,
                content=request_data if isinstance(request_data, str) else None
            )

            typer.echo(f"\nResponse Status: {response.status_code}")
            typer.echo(f"Response Headers:")
            for key, value in response.headers.items():
                typer.echo(f"  {key}: {value}")

            typer.echo(f"\nResponse Body:")
            try:
                # Try to pretty-print JSON
                json_response = response.json()
                typer.echo(json.dumps(json_response, indent=2))
            except:
                # Fall back to text
                typer.echo(response.text)

    except httpx.RequestError as e:
        typer.secho(f"Request failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.secho(f"Error making proxy request: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)