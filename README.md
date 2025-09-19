# DantaLabs SDK

A Python SDK for interacting with the DantaLabs Maestro API, featuring agent management, bundle deployment, and execution capabilities.

## Documentation

- The `/docs` directory contains the content that powers the public documentation site. Start with `docs/content/index.mdx` for an overview of features.
- Command-line coverage lives in `docs/content/cli/commands.mdx`, which mirrors the behaviour of the `dlm` CLI shipped with this package.
- The Python API is documented inline; see `dantalabs/maestro/client.py` for the full `MaestroClient` surface area, including resource helpers and bundle tooling.

## Installation

```bash
pip install dantalabs
```

or for the latest development version

```bash
pip install git+https://github.com/DantaLabs/maestro-sdk.git
```
## Quick Start

### Configure credentials

```bash
# Interactive setup (writes ~/.maestro/config.json)
dlm setup
dlm status

# Prefer flags or environment variables in CI/CD
export MAESTRO_API_URL="https://dantalabs.com"
export MAESTRO_ORGANIZATION_ID="your-org-id"
export MAESTRO_AUTH_TOKEN="your-token"
```

Most commands accept `--url`, `--org-id`, and `--token` flags when you need to override the stored configuration temporarily.

### Instantiate the Python client

```python
from dantalabs.maestro import MaestroClient

client = MaestroClient(
    organization_id="your-org-id",
    base_url="https://dantalabs.com",
    token="your-token",
)

agents = client.list_agents()
```

### Deploy with the CLI

```bash
dlm deploy path/to/project \
  --name "document-worker" \
  --agent-type script \
  --service
```

`dlm deploy` packages your project, uploads the bundle, and (optionally) rolls the definition out as a managed container service. Use `--definition-only` to skip service deployment, `--no-service` to keep the bundle only, and `--schema-file` to include JSON schema metadata.

### Deploy programmatically

```python
agent_definition = client.create_and_upload_bundle(
    source_dir="./my-agent",
    name="My Agent",
    description="Agent description",
    include_requirements=True,
)

# Or split the steps
bundle_path = client.create_bundle(
    source_dir="./my-agent",
    output_path="./my-agent.zip",
    maestro_config={"entrypoint": "main.py", "version": "1.0.0"},
)

client.upload_agent_bundle(bundle_path=bundle_path, name="My Agent")
```

## Bundle Deployment

### Creating and Deploying Bundles

The SDK supports creating and deploying ZIP bundles containing your agent code and dependencies.

#### Using the CLI

- `dlm deploy path/to/project` – end-to-end pipeline that packages, uploads, and optionally deploys your agent as a managed service.
- `dlm create-bundle ./my-agent --output ./my-agent.zip` – create a ZIP archive locally without uploading.
- `dlm upload-bundle ./my-agent.zip --name "My Agent" --create-agent` – turn an existing bundle into an agent definition.
- `dlm update-bundle <definition-id> ./new-agent.zip` – replace the code for an existing definition.
- `dlm deploy-bundle ./my-agent.zip --name "My Agent" --service` – upload and (optionally) redeploy in a single step.
- `dlm download-definition-bundle <definition-id>` – fetch the currently deployed bundle for inspection.

The CLI persists state (IDs, credentials, recent deployments) to `.maestro_state.json` in your project root so subsequent commands can reuse the same resources.

#### Using the Python Client

```python
# Build a bundle with auto-detected requirements and optional maestro.yaml overrides
bundle_path = client.bundle_creator.create_bundle(
    source_dir="./my-agent",
    output_path="./my-agent.zip",
    include_requirements=True,
    install_dependencies=False,
    maestro_config={"entrypoint": "main.py", "version": "1.0.0"},
)

# Upload or update definitions through the BundleManager helper
definition = client.bundle_manager.upload_bundle(
    bundle_path=bundle_path,
    name="My Agent",
    description="Agent description",
    shareable=True,
)

client.bundle_manager.update_bundle(
    definition_id=definition.id,
    bundle_path="./updated-agent.zip",
    version="1.0.1",
)
```

### Bundle Structure

A typical agent bundle should have this structure:

```
my-agent/
├── main.py              # Entry point (configurable)
├── requirements.txt     # Dependencies (auto-detected)
├── pyproject.toml       # Alternative to requirements.txt
├── maestro.yaml         # Optional: bundle configuration
├── .env.example         # Example environment variables
└── src/                 # Your agent code
    ├── __init__.py
    └── agent_logic.py
```

### Requirements Handling

The SDK automatically detects and includes dependencies from:

- `requirements.txt` files
- `pyproject.toml` (both PEP 621 and Poetry formats)

Example `pyproject.toml`:
```toml
[project]
dependencies = [
    "requests>=2.28.0",
    "numpy>=1.21.0"
]

[tool.poetry.dependencies]
python = "^3.8"
requests = "^2.28.0"
numpy = "^1.21.0"
```

### Configuration Files

#### maestro.yaml
```yaml
entrypoint: main.py
description: My custom agent
version: 1.0.0
```

#### Schema files
Create a JSON file with the same name as your directory:
```json
{
  "input": {
    "type": "object",
    "properties": {
      "message": {"type": "string"}
    }
  },
  "output": {
    "type": "object",
    "properties": {
      "response": {"type": "string"}
    }
  }
}
```

## Python Client Overview

`MaestroClient` centralises access to Maestro resources:

- `client.organizations`, `client.agents`, `client.networks`, `client.executions`, `client.files`, and `client.utils` mirror the underlying REST resources with create/list/update helpers.
- `client.bundle_creator` packages source directories, auto-detecting requirements files and optionally injecting a `maestro.yaml` manifest.
- `client.bundle_manager` uploads, updates, and downloads bundles; it is what powers `create_and_upload_bundle` and other high-level helpers.
- `client.proxy_http` is preconfigured for the proxy base URL so containerised agents can be called directly.
- `client.get_managed_memory(name, agent_id, auto_save=True)` returns a persisted dict-like helper backed by the Maestro API.

## Agent Management

### Creating Agents

```python
# Create agent definition first
definition = client.create_agent_definition(AgentDefinitionCreate(
    name="My Agent",
    definition="print('Hello World')",
    definition_type="python"
))

# Create agent instance
agent = client.create_agent(AgentCreate(
    name="My Agent Instance",
    agent_type="script",
    agent_definition_id=definition.id
))
```

### Running Agents

```bash
# Set default agent
dlm use-agent AGENT_ID

# Run with input
dlm run-agent '{"message": "Hello"}'

# Run with input file
dlm run-agent --file input.json
```

```python
# Execute agent
result = client.execute_agent_code_sync(
    variables={"message": "Hello"},
    agent_id=agent_id
)
```

### Memory Management

```python
# Get managed memory for an agent
memory = client.get_managed_memory("session_data", agent_id=agent_id)

# Use like a dictionary
memory["user_preferences"] = {"theme": "dark"}
memory.save()  # Persist to server

# Auto-save mode
memory = client.get_managed_memory("session_data", agent_id=agent_id, auto_save=True)
memory["data"] = "value"  # Automatically saved
```

## CLI Overview

### Essentials

| Command | Purpose |
| --- | --- |
| `dlm setup` | Configure the CLI interactively or script via flags |
| `dlm status` | Verify API connectivity and stored credentials |
| `dlm set-url` | Override the default Maestro API base URL |
| `dlm version` | Print the SDK-packaged CLI version |

### Deploying Code (Unified Pipeline)

- `dlm deploy path/to/project --name "app" --service` packages, uploads, and deploys the project.
- Add `--definition-only` to skip container rollout, `--no-service` to retain just the bundle, and `--force-definition` to create a fresh definition every time.
- `--entrypoint`, `--version`, and `--schema-file` control metadata stored with the resulting definition and service.

### Bundle Workflows

- `dlm create-bundle ./my-agent --output ./my-agent.zip` packages source without uploading.
- `dlm upload-bundle bundle.zip --name my-agent` creates a definition from an existing archive.
- `dlm update-bundle <definition-id> bundle.zip` replaces the archive for an existing definition.
- `dlm deploy-bundle bundle.zip --name my-agent --service` uploads and optionally redeploys a service in one step.
- `dlm download-definition-bundle <definition-id>` retrieves the latest bundle for local inspection.

### Agent Management

| Command | What it does |
| --- | --- |
| `dlm list-agents` | List agents in the organisation (`--show-def` adds linked definitions) |
| `dlm list-definitions` | Enumerate agent definitions and metadata |
| `dlm create-agent` | Create an agent from a definition (interactive picker supported) |
| `dlm update-agent <id>` | Rename, retarget, or update secrets for an agent |
| `dlm use-agent [id]` | Persist a default agent in `.maestro_state.json` |
| `dlm run-agent '{"foo": "bar"}'` | Execute a script agent synchronously |

### Service Operations

- `dlm service deploy <agent-id> [--env-file path]` redeploys a container service.
- `dlm service deployment-status <agent-id>` reports Knative rollout state and endpoint URLs.
- `dlm service logs <agent-id>` streams structured logs (`--level`, `--limit`, `--instance`).
- `dlm service execute '{"input": 1}' --agent-id <id>` sends JSON payloads to the running service.
- `dlm service proxy <agent-id> /path --method POST --data '{"foo": "bar"}'` debugs arbitrary HTTP routes.
- `dlm service metrics` aggregates service health and utilisation data.
- `dlm service stop <agent-id>` / `dlm service status <agent-id>` remain for backwards compatibility.

### Built-In Databases

- `dlm agentdb` lists every agent and its managed PostgreSQL databases.
- `dlm agentdb list --agent <id>` narrows the output to a single agent.
- `dlm agentdb inspect --db <database-id> --show-connection --show-tables` reveals connection strings and schema information.
- `dlm agentdb connect --db <database-id>` opens a `psql`/`pgcli` session (use `--print-only` for credentials).

### Templates & Starters

`dlm init` clones official starter projects, while `dlm list-templates` shows what is currently available. Templates follow the `/health` on port 8080 contract and demonstrate how to consume the injected database credentials and Maestro API token.

## Advanced Features

### Organizations

```python
# Create organization
org = client.create_organization(OrganizationCreate(
    name="My Organization",
    email="admin@example.com"
))

# Manage members
members = client.get_organization_members()

# Generate invitation token
token_info = client.generate_invitation_token(
    is_single_use=True,
    expiration_days=7
)
```

### Networks

```python
# Generate network from prompt
network = client.generate_network(NetworkGenerationRequest(
    prompt="Create a data processing pipeline"
))

# List networks
networks = client.list_networks()
```

### File Operations

```python
# Upload files
with open("data.csv", "rb") as f:
    file_info = client.upload_file(
        file=f,
        filename="data.csv",
        content_type="text/csv"
    )
```

## Error Handling

```python
from dantalabs.maestro.exceptions import (
    MaestroApiError, 
    MaestroAuthError, 
    MaestroValidationError
)

try:
    agent = client.get_agent(agent_id)
except MaestroAuthError:
    print("Authentication failed")
except MaestroValidationError as e:
    print(f"Validation error: {e.validation_errors}")
except MaestroApiError as e:
    print(f"API error {e.status_code}: {e.error_detail}")
```

## Development

### Requirements

- Python 3.8+
- httpx
- pydantic
- typer
- PyYAML (for bundle functionality)
- tomli (for Python < 3.11)
