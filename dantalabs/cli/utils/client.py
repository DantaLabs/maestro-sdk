import typer
import os
from typing import Optional, Annotated
from uuid import UUID
from ..config import load_config
from ...maestro import MaestroClient
from ...maestro.exceptions import MaestroApiError, MaestroAuthError

# Client state for reuse across commands
state = {"client": None, "config": None}

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