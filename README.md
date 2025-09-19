# DantaLabs SDK

The DantaLabs SDK bundles the `dlm` command line tool and the `MaestroClient` Python library so that you can deploy, operate, and automate agents on the Maestro platform from one package.

## Documentation
- `dantalabs/docs/content/introduction.mdx` ships with the package and mirrors the public documentation entry point.
- `dantalabs/cli` contains the Typer application behind `dlm` and is the best place to explore command behaviour.
- `dantalabs/maestro/client.py` exposes the Python client surface area, including resource helpers, service deployment utilities, and managed memory support.

## Installation

```bash
pip install --upgrade dantalabs

# latest development build
pip install git+https://github.com/DantaLabs/maestro-sdk.git
```

Python 3.8 or newer is required.

## Quick Start

### 1. Configure credentials

```bash
dlm setup
dlm status

# non-interactive environments
export MAESTRO_API_URL="https://dantalabs.com"
export MAESTRO_ORGANIZATION_ID="<org-id>"
export MAESTRO_AUTH_TOKEN="<token>"
```

You can override any stored value per command with `--url`, `--org-id`, or `--token`.

### 2. Deploy through the unified pipeline

```bash
dlm deploy ./agents/document-worker \
  --name "document-worker" \
  --agent-type script \
  --service
```

`dlm deploy` packages your project into a temporary bundle, uploads it, and optionally deploys the resulting agent as a managed Knative service. Use:
- `--no-service` to keep the definition without rolling out a service
- `--definition-only` to skip creating an agent instance
- `--schema-file path/to/schema.json` to attach JSON schema metadata

### 3. Call Maestro from Python

```python
from dantalabs.maestro import MaestroClient

client = MaestroClient(
    organization_id="<org-id>",
    base_url="https://dantalabs.com",
    token="<token>",
)

agents = client.list_agents()
result = client.execute_agent_code_sync({"message": "Hello"}, agent_id=agents[0].id)
```

Managed memory, agent databases, file uploads, and network generation helpers are available through the same client instance.

## CLI Highlights
- **Essentials**: `dlm setup`, `dlm status`, `dlm version`, `dlm set-url`
- **Agents**: `dlm list-agents`, `dlm list-definitions`, `dlm create-agent`, `dlm update-agent`, `dlm use-agent`, `dlm run-agent`
- **Services**: `dlm service deploy`, `dlm service deployment-status`, `dlm service logs`, `dlm service execute`, `dlm service proxy`
- **Managed databases**: `dlm agentdb list`, `dlm agentdb inspect --show-connection`, `dlm agentdb connect --print-only`
- **Starters**: `dlm init` clones the latest templates and `dlm list-templates` enumerates what is available

Every command accepts the standard authentication overrides (`--org-id`, `--url`, `--token`).

## Python Client Highlights
- One `MaestroClient` instance exposes `agents`, `executions`, `networks`, `files`, and `utils` resource managers (`dantalabs/maestro/resources`).
- `execute_agent_code(...)` and `execute_agent_code_sync(...)` run script agents directly; `deploy_service(...)` launches Knative services programmatically.
- `client.list_agent_databases(...)`, `client.get_database_connection_info(...)`, and other helpers surface the managed PostgreSQL databases that back each agent.
- `client.get_managed_memory(...)` returns a dictionary-like object that persists state back to Maestro automatically when `auto_save=True`.
- File uploads (`upload_file`) and network scaffolding (`generate_network`) are available for enriching agent workflows.

## Legacy Bundle Utilities (deprecated)

The CLI will continue to ship legacy bundle helpers for a short period to ease migration, but the unified deployment pipeline replaces the old workflows:
- `dlm create-bundle`, `dlm upload-bundle`, `dlm deploy-bundle`, `dlm update-bundle`, and `dlm download-definition-bundle`
- `MaestroClient.create_bundle`, `upload_agent_bundle`, `create_and_upload_bundle`, and related helpers in `dantalabs/maestro/bundles`

Prefer `dlm deploy` (or the `/api/v1/agents/deploy` endpoint) for new automation.

## Development

Local development requires:
- Python >= 3.8
- httpx, pydantic, typer, python-dotenv, PyYAML, tomli (Python < 3.11), psycopg

Clone the repository, install dependencies into a virtualenv, and run the CLI with `python -m dantalabs.cli` for local testing.
