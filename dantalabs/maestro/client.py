import os
from typing import Optional, Union, Dict, Any, List
from uuid import UUID
from pydantic import EmailStr
from .http.base import HTTPClient
from .resources.organizations import OrganizationResource
from .resources.agents import AgentResource
from .resources.networks import NetworkResource
from .resources.executions import ExecutionResource
from .resources.files import FileResource, UtilityResource
from .bundles.creator import BundleCreator
from .bundles.manager import BundleManager
from .memory import ManagedMemory
from .exceptions import MaestroAuthError, MaestroApiError, MaestroError
from .models import *


class MaestroClient:
    """
    Python SDK Client for the Maestro API using Bearer Token Authentication.
    
    Main client for interacting with the Maestro platform, providing access to
    agents, networks, memory management, and other platform services.

    Input:
        organization_id (Union[UUID, str]): The UUID of the organization context for API calls.
        agent_id (Optional[Union[UUID, str]]): Default Agent ID for agent-specific calls. Defaults to None.
        base_url (Optional[str]): The base URL of the Maestro API. Reads from MAESTRO_API_URL env var if None.
        proxy_base_url (Optional[str]): The base URL for agent proxy services. Reads from MAESTRO_PROXY_BASE_URL env var if None.
        token (Optional[str]): The Bearer token for authentication. Reads from MAESTRO_AUTH_TOKEN env var if None.
        timeout (float): Request timeout in seconds. Defaults to 120.0.
        raise_for_status (bool): Whether to automatically raise MaestroApiError for non-2xx responses. Defaults to True.

    Raises:
        ValueError: If required parameters (organization_id, base_url, token) are missing or invalid.
        MaestroAuthError: If authentication fails during API calls.
        MaestroApiError: For other non-2xx API errors if raise_for_status is True.
        MaestroError: For general SDK or unexpected errors.
    """

    def __init__(
        self,
        organization_id: Union[UUID, str],
        agent_id: Optional[Union[UUID, str]] = None,
        base_url: Optional[str] = None,
        proxy_base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 120.0,
        raise_for_status: bool = True,
    ) -> None:
        try:
            self.organization_id: UUID = UUID(str(organization_id))
        except (ValueError, TypeError):
            raise ValueError("organization_id must be a valid UUID or UUID string.")

        self.agent_id: Optional[UUID] = None
        if agent_id is not None:
            try:
                self.agent_id = UUID(str(agent_id))
            except (ValueError, TypeError):
                raise ValueError(
                    "agent_id must be a valid UUID or UUID string if provided."
                )

        resolved_base_url = base_url or os.getenv("MAESTRO_API_URL")
        if not resolved_base_url:
            resolved_base_url = "https://dantalabs.com"

        self.proxy_base_url = proxy_base_url or os.getenv("MAESTRO_PROXY_BASE_URL")
        if not self.proxy_base_url:
            self.proxy_base_url = "https://dantalabs.app"

        resolved_token = token or os.getenv("MAESTRO_AUTH_TOKEN")
        if not resolved_token:
            print(
                "Warning: Maestro auth token not provided during initialization. Use set_token() before making API calls."
            )
            resolved_token = ""

        # Initialize HTTP client
        self.http = HTTPClient(
            resolved_base_url, resolved_token, timeout, raise_for_status
        )

        # Initialize proxy HTTP client for container agents
        self.proxy_http = HTTPClient(
            self.proxy_base_url, resolved_token, timeout, raise_for_status
        )

        # Initialize resource managers
        self.organizations = OrganizationResource(self.http, self.organization_id)
        self.agents = AgentResource(self.http, self.organization_id)
        self.networks = NetworkResource(self.http, self.organization_id)
        self.executions = ExecutionResource(self.http, self.organization_id)
        self.files = FileResource(self.http, self.organization_id)
        self.utils = UtilityResource(self.http)

        # Initialize bundle tools
        self.bundle_creator = BundleCreator()
        self.bundle_manager = BundleManager(self.http, self.organization_id)

    def set_token(self, token: str) -> None:
        """
        Sets or updates the authentication token.
        
        Input:
            token (str): New authentication token to use for API requests.
            
        Raises:
            ValueError: If token is empty or None.
        """
        if not token:
            raise ValueError("Token cannot be empty.")
        self.http._token = token
        self.proxy_http._token = token

    def clear_token(self) -> None:
        """
        Clears the current authentication token.
        
        Removes the authentication token from both main and proxy HTTP clients.
        """
        self.http._token = ""
        self.proxy_http._token = ""

    def _ensure_agent_id_set(self) -> UUID:
        """Checks if agent_id is set and returns it, otherwise raises ValueError."""
        if self.agent_id is None:
            raise ValueError(
                "This method requires the client to be initialized with an agent_id, or agent_id passed explicitly."
            )
        return self.agent_id

    # Organization methods (delegate to organizations resource)
    def create_organization(self, org_data: OrganizationCreate) -> OrganizationRead:
        """Creates a new organization."""
        return self.organizations.create(org_data)

    def verify_token_with_email(self, email: str, token: str) -> Dict[str, Any]:
        """Verifies a token with an email address to retrieve an organization ID."""
        return self.organizations.verify_token_with_email(email, token)

    def get_my_organizations(self) -> List[OrganizationRead]:
        """Gets a list of organizations the current user is a member of."""
        return self.organizations.list_my_organizations()

    def update_organization(
        self, organization_update: OrganizationUpdate
    ) -> OrganizationRead:
        """Updates the organization specified during client initialization."""
        return self.organizations.update(organization_update)

    def delete_organization(self) -> None:
        """Deletes the organization specified during client initialization."""
        return self.organizations.delete()

    def read_organization(self) -> OrganizationRead:
        """Reads the details of the organization specified during client initialization."""
        return self.organizations.get()

    def get_organization_members(self) -> List[OrganizationMember]:
        """Gets members of the organization specified during client initialization."""
        return self.organizations.get_members()

    def generate_invitation_token(
        self, is_single_use: bool = True, expiration_days: int = 7
    ) -> Dict[str, Any]:
        """Generates an invitation token for the current organization."""
        return self.organizations.generate_invitation_token(
            is_single_use, expiration_days
        )

    def join_organization(self, token: str) -> Dict[str, Any]:
        """Allows the current user to join an organization using an invitation token."""
        return self.organizations.join_organization(token)

    def delete_user_from_organization(self, user_id: UUID) -> Dict[str, Any]:
        """Removes a user from the organization specified during client initialization."""
        return self.organizations.delete_user_from_organization(user_id)

    # Agent Definition methods (delegate to agents resource)
    def create_agent_definition(
        self, agent_definition_data: AgentDefinitionCreate
    ) -> AgentDefinition:
        """Creates an agent definition within the current organization."""
        return self.agents.create_definition(agent_definition_data)

    def list_agent_definitions(
        self, name: Optional[str] = None
    ) -> List[AgentDefinition]:
        """Lists agent definitions within the current organization."""
        return self.agents.list_definitions(name)

    def get_agent_definition(self, definition_id: UUID) -> AgentDefinition:
        """Gets a specific agent definition by ID within the current organization."""
        return self.agents.get_definition(definition_id)

    def update_agent_definition(
        self, definition_id: UUID, definition_data: AgentDefinitionCreate
    ) -> AgentDefinition:
        """Updates an existing Agent Definition."""
        return self.agents.update_definition(definition_id, definition_data)

    # Agent methods (delegate to agents resource)
    def create_agent(self, agent_data: AgentCreate) -> Agent:
        """Creates an agent within the current organization."""
        return self.agents.create(agent_data)

    def list_agents(self, name: Optional[str] = None) -> List[Agent]:
        """Lists agents within the current organization."""
        return self.agents.list(name)

    def get_agent(self, agent_id: UUID) -> Agent:
        """Gets a specific agent by ID within the current organization."""
        return self.agents.get(agent_id)

    def update_agent(self, agent_id: UUID, agent_data: AgentUpdate) -> Agent:
        """Updates an existing Agent."""
        return self.agents.update(agent_id, agent_data)

    # Agent execution methods (delegate to agents resource)
    def execute_agent_code(
        self,
        input_variables: Dict[str, Any],
        agent_id: Optional[UUID] = None,
        executor_type: Optional[str] = None,
    ) -> CodeExecution:
        """Executes the code associated with an agent."""
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        return self.agents.execute_code(input_variables, agent_id_to_use)

    def execute_agent_code_sync(
        self,
        variables: Dict[str, Any],
        agent_id: Optional[UUID] = None,
        executor_type: Optional[str] = None,
    ) -> CodeExecution:
        """Executes the code associated with an agent synchronously."""
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        return self.agents.execute_code_sync(variables, agent_id_to_use)

    # Execution methods (delegate to executions resource)
    def get_execution_status(self, execution_id: UUID) -> CodeExecution:
        """Gets the status of a specific code execution within the organization."""
        return self.executions.get_status(execution_id)

    def list_executions(
        self, limit: int = 10, skip: int = 0, agent_id: Optional[UUID] = None
    ) -> List[CodeExecution]:
        """Lists code executions within the current organization."""
        return self.executions.list(limit, skip, agent_id)

    # Network methods (delegate to networks resource)
    def generate_network(self, request: NetworkGenerationRequest) -> NetworkResponse:
        """Generates a network based on a prompt within the current organization."""
        return self.networks.generate(request)

    def list_networks(self, skip: int = 0, limit: int = 100) -> NetworkListResponse:
        """Lists networks within the current organization."""
        return self.networks.list(skip, limit)

    def get_network(self, network_id: UUID) -> NetworkResponse:
        """Gets a specific network by ID within the current organization."""
        return self.networks.get(network_id)

    def delete_network(self, network_id: UUID) -> None:
        """Deletes a specific network by ID within the current organization."""
        return self.networks.delete(network_id)

    # File methods (delegate to files resource)
    def upload_file(
        self, file, filename: str, content_type: str, **kwargs
    ) -> ReturnFile:
        """Upload a file associated with the client's organization."""
        return self.files.upload(file, filename, content_type, **kwargs)

    # Bundle methods (delegate to bundle tools)
    def create_bundle(self, source_dir: str, **kwargs) -> str:
        """Creates a ZIP bundle from a source directory for agent deployment."""
        return self.bundle_creator.create_bundle(source_dir, **kwargs)

    def upload_agent_bundle(
        self, bundle_path: str, name: str, **kwargs
    ) -> AgentDefinition:
        """Uploads a ZIP bundle to create a new Agent Definition."""
        return self.bundle_manager.upload_bundle(bundle_path, name, **kwargs)

    def update_agent_bundle(
        self, definition_id: UUID, bundle_path: str, **kwargs
    ) -> AgentDefinition:
        """Updates an existing bundled Agent Definition with a new ZIP bundle."""
        return self.bundle_manager.update_bundle(definition_id, bundle_path, **kwargs)

    def download_agent_definition_bundle(self, definition_id: UUID) -> bytes:
        """Downloads the bundle for a specific agent definition."""
        return self.bundle_manager.download_bundle(definition_id)

    def create_and_upload_bundle(
        self, source_dir: str, name: str, **kwargs
    ) -> AgentDefinition:
        """Creates a bundle from a source directory and uploads it to create an Agent Definition."""
        cleanup_bundle = kwargs.pop("cleanup_bundle", True)
        bundle_path = None
        try:
            # Create the bundle
            bundle_path = self.bundle_creator.create_bundle(
                source_dir,
                **{
                    k: v
                    for k, v in kwargs.items()
                    if k
                    in [
                        "include_requirements",
                        "install_dependencies",
                        "maestro_config",
                    ]
                },
            )

            # Upload the bundle
            return self.bundle_manager.upload_bundle(
                bundle_path,
                name,
                **{
                    k: v
                    for k, v in kwargs.items()
                    if k
                    not in [
                        "include_requirements",
                        "install_dependencies",
                        "maestro_config",
                        "cleanup_bundle",
                    ]
                },
            )

        finally:
            # Clean up the temporary bundle file if requested
            if cleanup_bundle and bundle_path and os.path.exists(bundle_path):
                try:
                    os.remove(bundle_path)
                except Exception:
                    pass

    def create_and_upload_bundle_as_image(
        self, source_dir: str, name: str, **kwargs
    ) -> AgentDefinition:
        """Creates a bundle from a source directory and uploads it as a container image to create an Agent Definition."""
        cleanup_bundle = kwargs.pop("cleanup_bundle", True)
        bundle_path = None
        try:
            # For image-based deployments, don't install dependencies in the bundle
            # They will be installed during Docker image build instead
            bundle_kwargs = {
                k: v
                for k, v in kwargs.items()
                if k
                in ["include_requirements", "install_dependencies", "maestro_config"]
            }
            bundle_kwargs["install_dependencies"] = (
                False  # Force disable for image deployments
            )
            bundle_kwargs["include_requirements"] = (
                True  # Always include requirements.txt
            )

            # Create the bundle
            bundle_path = self.bundle_creator.create_bundle(source_dir, **bundle_kwargs)

            # Upload the bundle as image
            return self.bundle_manager.upload_bundle_as_image(
                bundle_path,
                name,
                **{
                    k: v
                    for k, v in kwargs.items()
                    if k
                    not in [
                        "include_requirements",
                        "install_dependencies",
                        "maestro_config",
                        "cleanup_bundle",
                    ]
                },
            )

        finally:
            # Clean up the temporary bundle file if requested
            if cleanup_bundle and bundle_path and os.path.exists(bundle_path):
                try:
                    os.remove(bundle_path)
                except Exception:
                    pass

    def get_bundle_download_url(self, agent_id: Optional[UUID] = None) -> str:
        """Get a temporary download URL for the agent's bundle."""
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        return self.bundle_manager.get_bundle_download_url(agent_id_to_use)

    def download_bundle(
        self, target_dir: Optional[str] = None, agent_id: Optional[UUID] = None
    ) -> str:
        """Download the agent's bundle to a local directory."""
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        return self.bundle_manager.download_agent_bundle(target_dir, agent_id_to_use)

    def extract_bundle(self, bundle_path: str, target_dir: Optional[str] = None) -> str:
        """Extract a downloaded bundle to a directory."""
        return self.bundle_manager.extract_bundle(bundle_path, target_dir)

    # Memory Management methods
    def get_managed_memory(
        self, memory_name: str, agent_id: Optional[UUID] = None, **kwargs
    ) -> ManagedMemory:
        """Gets a ManagedMemory instance for interacting with a specific agent's memory."""
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        return ManagedMemory(
            client=self, agent_id=agent_id_to_use, memory_name=memory_name, **kwargs
        )

    def add_memory_to_agent(
        self, memory_data: dict, agent_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Adds a new memory record and associates it with an agent."""
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        payload = {"memory_data": memory_data}
        return self.http.request(
            method="POST",
            path="/api/v1/agents/{agent_id}/memories/",
            path_params={"agent_id": agent_id_to_use},
            json_data=payload,
            expected_status=200,
            response_model=None,
            return_type="json",
            organization_id=self.organization_id,
        )

    def get_agent_memories(
        self, agent_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """Gets a list of memories associated with a specific agent."""
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        return self.http.request(
            method="GET",
            path="/api/v1/agents/{agent_id}/memories/",
            path_params={"agent_id": agent_id_to_use},
            expected_status=200,
            response_model=None,
            return_type="json",
            organization_id=self.organization_id,
        )

    def _get_memory_by_name_raw(
        self, memory_name: str, agent_id: Optional[UUID] = None
    ) -> Optional[Dict[str, Any]]:
        """Internal helper to fetch raw memory data by name for a specific agent."""
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        try:
            return self.http.request(
                method="GET",
                path="/api/v1/agents/{agent_id}/memories/by-name/{memory_name}",
                path_params={"agent_id": agent_id_to_use, "memory_name": memory_name},
                expected_status=200,
                response_model=None,
                return_type="json",
                organization_id=self.organization_id,
            )
        except MaestroApiError as e:
            if e.status_code == 404:
                return None
            raise

    def get_memory(self, memory_id: UUID) -> Dict[str, Any]:
        """Gets details of a specific memory by its ID."""
        return self.http.request(
            method="GET",
            path="/api/v1/agents/memories/{memory_id}",
            path_params={"memory_id": memory_id},
            expected_status=200,
            response_model=None,
            return_type="json",
            organization_id=self.organization_id,
        )

    def update_memory(
        self, memory_id: UUID, update_data: dict, agent_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Update an existing memory record."""
        query_params = {}
        if agent_id:
            query_params["agent_id"] = str(agent_id)

        return self.http.request(
            method="PUT",
            path="/api/v1/agents/memories/{memory_id}",
            path_params={"memory_id": memory_id},
            query_params=query_params if query_params else None,
            json_data=update_data,
            expected_status=200,
            response_model=None,
            return_type="json",
            organization_id=self.organization_id,
        )

    def delete_memory(self, memory_id: UUID) -> None:
        """Deletes a memory record by its ID."""
        return self.http.request(
            method="DELETE",
            path="/api/v1/agents/memories/{memory_id}",
            path_params={"memory_id": memory_id},
            expected_status=204,
            return_type="none",
            organization_id=self.organization_id,
        )

    def disconnect_memory_from_agent(
        self, memory_id: UUID, agent_id: Optional[UUID] = None
    ) -> None:
        """Disconnects a memory from an agent without deleting the memory itself."""
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        return self.http.request(
            method="POST",
            path="/api/v1/agents/{agent_id}/disconnect-memory/{memory_id}",
            path_params={"agent_id": agent_id_to_use, "memory_id": memory_id},
            expected_status=204,
            return_type="none",
            organization_id=self.organization_id,
        )

    def query_agent(
        self,
        agent_identifier: Union[UUID, str],
        request: Dict[str, Any],
        path: str = "",
    ) -> Union[Dict[str, Any], CodeExecution]:
        """
        Query an agent by name or ID with unified interface for both script and container agents.

        Args:
            agent_identifier: Agent ID (UUID) or agent name (str)
            request: Request data to send to the agent
            path: Path for container agent requests (e.g., "/api/chat")

        Returns:
            For script agents: CodeExecution object
            For container agents: JSON response from the HTTP request
        """
        # Get agent by ID or name
        if isinstance(agent_identifier, str) and not self._is_uuid(agent_identifier):
            agent = self.agents.get_by_name(agent_identifier)
        else:
            agent_id = (
                UUID(str(agent_identifier))
                if not isinstance(agent_identifier, UUID)
                else agent_identifier
            )
            agent = self.agents.get(agent_id)

        # Get the agent definition to check if it's a bundle (container) agent
        agent_definition = self.agents.get_definition(agent.agent_definition_id)

        # Check if agent is a bundle (container) agent
        if agent_definition.is_bundle:
            # Container agent - make HTTP request via proxy service
            return self._query_container_agent(agent.id, request, path)
        else:
            # Script agent - execute via run endpoint
            return self._query_script_agent(agent.id, request)

    def _is_uuid(self, value: str) -> bool:
        """Check if a string is a valid UUID."""
        try:
            UUID(value)
            return True
        except (ValueError, TypeError):
            return False

    def _query_container_agent(
        self, agent_id: UUID, request: Dict[str, Any], path: str = ""
    ) -> Dict[str, Any]:
        """Handle queries to container agents via agent-specific subdomain."""
        # Default to POST request, but allow customization
        method = request.pop("method", "POST") if "method" in request else "POST"

        # Ensure path starts with /
        if path and not path.startswith("/"):
            path = "/" + path

        # Create agent-specific subdomain URL: agent_id.dantalabs.app
        agent_subdomain = f"https://{agent_id}.{self.proxy_base_url.replace('https://', '').replace('http://', '')}"

        # Use a direct HTTP client for the agent subdomain
        import httpx

        with httpx.Client(timeout=self.proxy_http._timeout) as client:
            headers = {}
            if self.proxy_http._token:
                headers["Authorization"] = f"Bearer {self.proxy_http._token}"

            response = client.request(
                method=method,
                url=f"{agent_subdomain}{path}",
                json=request,
                headers=headers,
            )

            response.raise_for_status()

            # Try to return JSON if possible, otherwise return text
            try:
                return response.json()
            except:
                return {"response": response.text, "status_code": response.status_code}

    def _query_script_agent(
        self, agent_id: UUID, request: Dict[str, Any]
    ) -> CodeExecution:
        """Handle queries to script agents via execution endpoint."""
        return self.agents.execute_code_sync(request, agent_id)

    # Agent Service methods (delegate to agents resource)
    def deploy_service(
        self,
        agent_id: UUID,
        executor_type: Optional[str] = None,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Deploy an agent as a Knative service for auto-scaling."""
        return self.agents.deploy_service(agent_id, executor_type, env_vars)

    def get_deployment_status(self, agent_id: UUID) -> Dict[str, Any]:
        """Get the deployment status of an agent service in Knative."""
        return self.agents.get_deployment_status(agent_id)

    def start_service(
        self, agent_id: UUID, env_vars: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """[DEPRECATED] Start a long-running agent service. Use deploy_service() for Knative agents."""
        return self.agents.start_service(agent_id, env_vars)

    def stop_service(self, agent_id: UUID) -> None:
        """Stop a running agent service."""
        return self.agents.stop_service(agent_id)

    def get_service_status(self, agent_id: UUID) -> Dict[str, Any]:
        """[DEPRECATED] Get the status of a running agent service. Use get_deployment_status() for Knative agents."""
        return self.agents.get_service_status(agent_id)

    def list_services(self) -> List[Dict[str, Any]]:
        """List all running agent services for the organization."""
        return self.agents.list_services()

    def execute_via_service(
        self,
        agent_id: UUID,
        input_variables: Dict[str, Any],
        function_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute a request via a running agent service."""
        return self.agents.execute_via_service(agent_id, input_variables, function_name)

    def get_service_logs(
        self,
        agent_id: UUID,
        instance_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        log_level: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get logs for a specific agent service."""
        return self.agents.get_service_logs(
            agent_id, instance_id, limit, offset, log_level
        )

    def get_service_metrics(self) -> Dict[str, Any]:
        """Get metrics about running agent services."""
        return self.agents.get_service_metrics()

    def get_service_health(self, agent_id: UUID) -> Dict[str, Any]:
        """Get health information for an agent service."""
        return self.agents.get_service_health(agent_id)

    # Agent Database methods (delegate to agents resource)
    def create_agent_database(
        self, agent_id: UUID, database_request
    ) -> "AgentDatabase":
        """Create a database for an agent."""
        return self.agents.create_database(agent_id, database_request)

    def list_agent_databases(self, agent_id: UUID) -> List["AgentDatabase"]:
        """List all databases for an agent."""
        return self.agents.list_databases(agent_id)

    def get_agent_database(self, agent_id: UUID, database_id: UUID) -> "AgentDatabase":
        """Get a specific database for an agent."""
        return self.agents.get_database(agent_id, database_id)

    def delete_agent_database(
        self, agent_id: UUID, database_id: UUID
    ) -> Dict[str, Any]:
        """Delete a database for an agent."""
        return self.agents.delete_database(agent_id, database_id)

    def execute_database_sql(
        self, agent_id: UUID, database_id: UUID, sql_request
    ) -> Dict[str, Any]:
        """Execute SQL on an agent's database."""
        return self.agents.execute_sql(agent_id, database_id, sql_request)

    def list_database_tables(
        self, agent_id: UUID, database_id: UUID
    ) -> List["TableInfo"]:
        """List all tables in an agent's database."""
        return self.agents.list_database_tables(agent_id, database_id)

    def get_database_table_schema(
        self, agent_id: UUID, database_id: UUID, table_name: str
    ) -> Dict[str, Any]:
        """Get the schema for a specific table in an agent's database."""
        return self.agents.get_table_schema(agent_id, database_id, table_name)

    def get_database_connection_info(
        self, agent_id: UUID, database_id: UUID
    ) -> Dict[str, Any]:
        """Get transparent connection information for an agent database."""
        return self.agents.get_database_connection_info(agent_id, database_id)

    # Utility methods (delegate to utils resource)
    def health_check(self) -> bool:
        """Performs a health check on the Maestro API."""
        return self.utils.health_check()

    def test_email(self, email_to: EmailStr) -> Message:
        """Sends a test email via the Maestro service."""
        return self.utils.test_email(email_to)

    # Lifecycle methods
    def close(self):
        """Closes the underlying HTTP client connections."""
        self.http.close()
        self.proxy_http.close()

    def __enter__(self):
        """Prepares the client when used in a 'with' statement."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensures the client is closed when exiting a 'with' block."""
        self.close()
