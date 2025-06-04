# DantaLabs SDK

A Python SDK for interacting with the DantaLabs Maestro API, featuring agent management, bundle deployment, and execution capabilities.

## Installation

```bash
pip install dantalabs
```

## Quick Start

### Configuration

First, configure your credentials:

```bash
# Interactive setup
dlm setup

# Or set environment variables
export MAESTRO_API_URL="https://dantalabs.com"
export MAESTRO_ORGANIZATION_ID="your-org-id"
export MAESTRO_AUTH_TOKEN="your-token"
```

### Basic Usage

```python
from dantalabs.maestro import MaestroClient

# Initialize client
client = MaestroClient(
    organization_id="your-org-id",
    base_url="https://dantalabs.com",
    token="your-token"
)

# List agents
agents = client.list_agents()
```

## Bundle Deployment

### Creating and Deploying Bundles

The SDK supports creating and deploying ZIP bundles containing your agent code and dependencies.

#### Using the CLI

**Deploy a bundle from a directory (recommended):**
```bash
dlm deploy-bundle ./my-agent --name "My Agent" --desc "Agent description"
```

**Create a bundle locally:**
```bash
dlm create-bundle ./my-agent --output ./my-agent.zip
```

**Upload an existing bundle:**
```bash
dlm upload-bundle ./my-agent.zip --name "My Agent" --create-agent
```

**Update an existing bundle:**
```bash
dlm update-bundle DEFINITION_ID ./new-agent.zip
```

#### Using the Python Client

```python
# Create and upload bundle in one step
agent_definition = client.create_and_upload_bundle(
    source_dir="./my-agent",
    name="My Agent",
    description="Agent description",
    include_requirements=True  # Auto-include requirements.txt or pyproject.toml
)

# Or create bundle locally first
bundle_path = client.create_bundle(
    source_dir="./my-agent",
    output_path="./my-agent.zip",
    maestro_config={
        "entrypoint": "main.py",
        "version": "1.0.0"
    }
)

# Then upload it
agent_definition = client.upload_agent_bundle(
    bundle_path=bundle_path,
    name="My Agent"
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

## CLI Commands

| Command | Description |
|---------|-------------|
| `dlm setup` | Configure credentials |
| `dlm deploy` | Deploy single Python file as agent |
| `dlm create-bundle` | Create ZIP bundle from directory |
| `dlm upload-bundle` | Upload bundle to create agent definition |
| `dlm deploy-bundle` | Create and upload bundle in one step |
| `dlm update-bundle` | Update existing bundled agent definition |
| `dlm download-definition-bundle` | Download bundle for agent definition |
| `dlm create-agent` | Create agent from existing definition |
| `dlm update-agent` | Update existing agent |
| `dlm use-agent` | Set default agent for commands |
| `dlm run-agent` | Execute agent with input |

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

