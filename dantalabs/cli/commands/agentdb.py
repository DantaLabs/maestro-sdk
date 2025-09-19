import typer
import json
import subprocess
import sys
from typing import Optional, Annotated, Dict, Any
from uuid import UUID
from pathlib import Path
from ..utils.client import get_client
from ..config import load_config
from ...maestro.exceptions import MaestroApiError, MaestroValidationError

app = typer.Typer(help="Manage agent databases and connections")

@app.command("list")
def list_agent_databases(
    agent_id: Annotated[Optional[str], typer.Option("--agent", "-a", help="Agent ID to list databases for")] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """List agent databases. If no agent specified, lists all agents with databases."""
    client = get_client(org_id, url, token)

    try:
        if agent_id:
            # List databases for specific agent
            try:
                agent_uuid = UUID(agent_id)
            except ValueError:
                typer.secho(f"Error: '{agent_id}' is not a valid agent ID (should be a UUID).", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)

            # Get agent details
            try:
                agent = client.get_agent(agent_uuid)
                typer.echo(f"Databases for agent: {agent.name} (ID: {agent_uuid})")
            except MaestroApiError:
                typer.echo(f"Databases for agent ID: {agent_uuid}")

            # Get databases for this agent
            databases = client.list_agent_databases(agent_uuid)

            if not databases:
                typer.echo("No databases found for this agent.")
                return

            typer.echo()
            for db in databases:
                typer.echo(f"• {db.name} (ID: {db.id})")
                if db.description:
                    typer.echo(f"  Description: {db.description}")
                typer.echo(f"  Template: {db.database_template or 'default'}")
                typer.echo(f"  Created: {db.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
                typer.echo()
        else:
            # List all agents and their databases
            agents = client.list_agents()

            if not agents:
                typer.echo("No agents found.")
                return

            typer.echo("Agents and their databases:")
            typer.echo()

            for agent in agents:
                try:
                    databases = client.list_agent_databases(agent.id)
                    db_count = len(databases) if databases else 0

                    typer.echo(f"• {agent.name} (ID: {agent.id}) - {db_count} database(s)")

                    if databases:
                        for db in databases:
                            typer.echo(f"  └─ {db.name} (Template: {db.database_template or 'default'})")
                    else:
                        typer.echo(f"  └─ No databases")
                    typer.echo()
                except MaestroApiError as e:
                    typer.echo(f"  └─ Error fetching databases: {e}")
                    typer.echo()

    except MaestroApiError as e:
        typer.secho(f"API Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("inspect")
def inspect_database(
    database_id: Annotated[Optional[str], typer.Option("--database-id", "--db", help="Database ID to inspect")] = None,
    agent_id: Annotated[Optional[str], typer.Option("--agent", "-a", help="Agent ID (if database-id not provided, will list databases)")] = None,
    show_connection: Annotated[bool, typer.Option("--show-connection", "-c", help="Show connection information")] = False,
    show_tables: Annotated[bool, typer.Option("--show-tables", "-t", help="Show database tables")] = False,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Inspect an agent database and show detailed information."""
    client = get_client(org_id, url, token)

    try:
        # If no database_id provided, help user select one
        if not database_id:
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
                typer.secho("Error: No database ID or agent ID provided. Use --database-id or --agent.", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)

            # List databases for agent selection
            databases = client.list_agent_databases(agent_id_to_use)
            if not databases:
                typer.echo("No databases found for this agent.")
                return

            typer.echo("Available databases:")
            for i, db in enumerate(databases, 1):
                typer.echo(f"{i}) {db.name} - {db.description or 'No description'} (ID: {db.id})")

            selection = typer.prompt("Select database number", type=int)
            if selection < 1 or selection > len(databases):
                typer.secho(f"Invalid selection. Please enter a number between 1 and {len(databases)}.", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)

            selected_db = databases[selection - 1]
            database_id = str(selected_db.id)

        # Convert database_id to UUID
        try:
            db_uuid = UUID(database_id)
        except ValueError:
            typer.secho(f"Error: '{database_id}' is not a valid database ID (should be a UUID).", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        # Get database details - first find which agent owns this database
        database = None
        final_agent_id = None
        if agent_id_to_use:
            # We have a specific agent, check if it owns this database
            try:
                database = client.get_agent_database(agent_id_to_use, db_uuid)
                final_agent_id = agent_id_to_use
            except:
                # Database not found for this agent
                pass

        if not database:
            # Search through all agents to find which one owns this database
            agents = client.list_agents()
            for agent in agents:
                try:
                    databases = client.list_agent_databases(agent.id)
                    for db in databases:
                        if db.id == db_uuid:
                            database = db
                            final_agent_id = agent.id
                            break
                    if database:
                        break
                except:
                    continue

        if not database:
            typer.secho(f"Database {database_id} not found.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Database: {database.name}")
        typer.echo(f"ID: {database.id}")
        if database.description:
            typer.echo(f"Description: {database.description}")
        typer.echo(f"Template: {database.database_template or 'default'}")
        typer.echo(f"Agent ID: {database.agent_id}")
        typer.echo(f"Organization ID: {database.organization_id}")
        typer.echo(f"Created: {database.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        typer.echo()

        # Show connection information if requested
        if show_connection:
            try:
                connection_info = client.get_database_connection_info(final_agent_id, db_uuid)
                typer.secho("Connection Information:", fg=typer.colors.BLUE)
                typer.echo(f"Architecture: {connection_info.get('architecture', 'N/A')}")
                typer.echo(f"Security Mode: {connection_info.get('security_mode', 'N/A')}")
                if connection_info.get('connection_string'):
                    # Redact password from connection string for display
                    conn_str = connection_info['connection_string']
                    if '://' in conn_str and '@' in conn_str:
                        parts = conn_str.split('://', 1)
                        if len(parts) == 2:
                            scheme, rest = parts
                            if '@' in rest:
                                creds, host_part = rest.split('@', 1)
                                if ':' in creds:
                                    user, _ = creds.split(':', 1)
                                    redacted_conn = f"{scheme}://{user}:[REDACTED]@{host_part}"
                                else:
                                    redacted_conn = conn_str
                            else:
                                redacted_conn = conn_str
                        else:
                            redacted_conn = conn_str
                    else:
                        redacted_conn = conn_str
                    typer.echo(f"Connection String: {redacted_conn}")
                typer.echo()
            except MaestroApiError as e:
                typer.secho(f"Could not fetch connection info: {e}", fg=typer.colors.YELLOW, err=True)

        # Show tables if requested
        if show_tables:
            try:
                tables = client.list_database_tables(final_agent_id, db_uuid)
                typer.secho("Tables:", fg=typer.colors.BLUE)
                if tables:
                    for table in tables:
                        typer.echo(f"• {table.get('name', 'N/A')} ({table.get('type', 'TABLE')})")
                        if table.get('comment'):
                            typer.echo(f"  Description: {table['comment']}")
                else:
                    typer.echo("No tables found.")
                typer.echo()
            except MaestroApiError as e:
                typer.secho(f"Could not fetch table list: {e}", fg=typer.colors.YELLOW, err=True)

    except MaestroApiError as e:
        typer.secho(f"API Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command("connect")
def connect_to_database(
    database_id: Annotated[Optional[str], typer.Option("--database-id", "--db", help="Database ID to connect to")] = None,
    agent_id: Annotated[Optional[str], typer.Option("--agent", "-a", help="Agent ID (if database-id not provided, will list databases)")] = None,
    client_tool: Annotated[Optional[str], typer.Option("--client", "-c", help="Database client to use (psql, pgcli, dbeaver, etc.)")] = "psql",
    print_only: Annotated[bool, typer.Option("--print-only", "-p", help="Only print connection information, don't launch client")] = False,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Connect to an agent database using a database client."""
    client = get_client(org_id, url, token)

    try:
        # If no database_id provided, help user select one
        if not database_id:
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
                typer.secho("Error: No database ID or agent ID provided. Use --database-id or --agent.", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)

            # List databases for agent selection
            databases = client.list_agent_databases(agent_id_to_use)
            if not databases:
                typer.echo("No databases found for this agent.")
                return

            typer.echo("Available databases:")
            for i, db in enumerate(databases, 1):
                typer.echo(f"{i}) {db.name} - {db.description or 'No description'} (ID: {db.id})")

            selection = typer.prompt("Select database number", type=int)
            if selection < 1 or selection > len(databases):
                typer.secho(f"Invalid selection. Please enter a number between 1 and {len(databases)}.", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)

            selected_db = databases[selection - 1]
            database_id = str(selected_db.id)

        # Convert database_id to UUID
        try:
            db_uuid = UUID(database_id)
        except ValueError:
            typer.secho(f"Error: '{database_id}' is not a valid database ID (should be a UUID).", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        # Get database details and find agent - similar logic to inspect
        database = None
        final_agent_id = None
        if agent_id_to_use:
            # We have a specific agent, check if it owns this database
            try:
                database = client.get_agent_database(agent_id_to_use, db_uuid)
                final_agent_id = agent_id_to_use
            except:
                # Database not found for this agent
                pass

        if not database:
            # Search through all agents to find which one owns this database
            agents = client.list_agents()
            for agent in agents:
                try:
                    databases = client.list_agent_databases(agent.id)
                    for db in databases:
                        if db.id == db_uuid:
                            database = db
                            final_agent_id = agent.id
                            break
                    if database:
                        break
                except:
                    continue

        if not database:
            typer.secho(f"Database {database_id} not found.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        # Get connection information
        connection_info = client.get_database_connection_info(final_agent_id, db_uuid)
        connection_string = connection_info.get('connection_string')

        if not connection_string:
            typer.secho("Error: No connection string available for this database.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        # Parse connection string to extract components
        # Format: postgresql+psycopg://user:pass@host:port/db?options
        conn_components = _parse_connection_string(connection_string)

        if print_only:
            typer.echo("Connection Information:")
            typer.echo(f"Host: {conn_components['host']}")
            typer.echo(f"Port: {conn_components['port']}")
            typer.echo(f"Database: {conn_components['database']}")
            typer.echo(f"Username: {conn_components['username']}")
            typer.echo(f"Password: {conn_components['password']}")
            if conn_components.get('options'):
                typer.echo(f"Options: {conn_components['options']}")
            typer.echo()
            typer.echo("Full connection string:")
            typer.echo(connection_string)
            return

        # Launch the database client
        _launch_database_client(client_tool, conn_components)

    except MaestroApiError as e:
        typer.secho(f"API Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

def _parse_connection_string(connection_string: str) -> Dict[str, str]:
    """Parse a PostgreSQL connection string into components."""
    import re
    from urllib.parse import parse_qs, urlparse

    # Handle postgresql+psycopg:// scheme
    if connection_string.startswith('postgresql+psycopg://'):
        # Convert to standard postgresql:// for parsing
        parsed_url = connection_string.replace('postgresql+psycopg://', 'postgresql://')
    else:
        parsed_url = connection_string

    # Parse URL
    parsed = urlparse(parsed_url)

    # Extract query parameters for options
    options = ""
    if parsed.query:
        # Handle options parameter specifically
        query_params = parse_qs(parsed.query)
        if 'options' in query_params:
            options = query_params['options'][0]

    return {
        'host': parsed.hostname or 'localhost',
        'port': str(parsed.port or 5432),
        'database': parsed.path.lstrip('/') if parsed.path else '',
        'username': parsed.username or '',
        'password': parsed.password or '',
        'options': options
    }

def _launch_database_client(client_tool: str, conn_components: Dict[str, str]):
    """Launch the specified database client with connection parameters."""
    host = conn_components['host']
    port = conn_components['port']
    database = conn_components['database']
    username = conn_components['username']
    password = conn_components['password']

    if client_tool.lower() == 'psql':
        # Use psql
        cmd = [
            'psql',
            f'postgresql://{username}:{password}@{host}:{port}/{database}'
        ]

        typer.echo(f"Connecting to database using psql...")
        typer.echo(f"Host: {host}:{port}, Database: {database}, User: {username}")

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            typer.secho(f"Error launching psql: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        except FileNotFoundError:
            typer.secho("Error: psql not found. Please install PostgreSQL client tools.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

    elif client_tool.lower() == 'pgcli':
        # Use pgcli (enhanced PostgreSQL CLI)
        cmd = [
            'pgcli',
            f'postgresql://{username}:{password}@{host}:{port}/{database}'
        ]

        typer.echo(f"Connecting to database using pgcli...")
        typer.echo(f"Host: {host}:{port}, Database: {database}, User: {username}")

        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            typer.secho(f"Error launching pgcli: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        except FileNotFoundError:
            typer.secho("Error: pgcli not found. Install with: pip install pgcli", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

    else:
        typer.secho(f"Unsupported client tool: {client_tool}", fg=typer.colors.RED, err=True)
        typer.echo("Supported clients: psql, pgcli")
        typer.echo()
        typer.echo("Manual connection information:")
        typer.echo(f"Host: {host}")
        typer.echo(f"Port: {port}")
        typer.echo(f"Database: {database}")
        typer.echo(f"Username: {username}")
        typer.echo(f"Password: {password}")
        raise typer.Exit(code=1)

# Default command when just running "dlm agentdb"
@app.callback(invoke_without_command=True)
def agentdb_main(
    ctx: typer.Context,
    agent_id: Annotated[Optional[str], typer.Option("--agent", "-a", help="Agent ID to show databases for")] = None,
    # Client options
    org_id: Annotated[Optional[UUID], typer.Option("--org-id", help="Maestro Organization ID (Overrides env var).")] = None,
    url: Annotated[Optional[str], typer.Option("--url", help="Maestro API Base URL (Overrides env var).")] = None,
    token: Annotated[Optional[str], typer.Option("--token", help="Maestro Auth Token (Overrides env var).")] = None,
):
    """Main agentdb command. Lists agents and their databases."""
    if ctx.invoked_subcommand is None:
        # If no subcommand provided, default to listing
        list_agent_databases(agent_id, org_id, url, token)