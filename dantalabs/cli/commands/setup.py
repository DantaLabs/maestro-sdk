import typer
from typing import Optional, Annotated
from uuid import UUID
from ..config import load_config, save_config
from ...maestro import MaestroClient
from ...maestro.exceptions import MaestroAuthError, MaestroApiError

app = typer.Typer()

@app.command()
def setup_command(
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
    typer.secho(f"Configuring Maestro CLI settings...", fg=typer.colors.CYAN)

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
    typer.secho(f" ~/.maestro/config.json", fg=typer.colors.WHITE, bold=True)
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