import os
from typing import Optional, Union
from uuid import UUID
from .http.base import HTTPClient
from .resources.organizations import OrganizationResource
from .resources.agents import AgentResource
from .exceptions import MaestroAuthError, MaestroApiError, MaestroError

class MaestroClient:
    """
    Python SDK Client for the Maestro API using Bearer Token Authentication.

    Args:
        organization_id (Union[UUID, str]): The UUID of the organization context for API calls.
        agent_id (Optional[Union[UUID, str]], optional): Default Agent ID for agent-specific calls. Defaults to None.
        base_url (Optional[str], optional): The base URL of the Maestro API. Reads from MAESTRO_API_URL env var if None. Defaults to None.
        token (Optional[str], optional): The Bearer token for authentication. Reads from MAESTRO_AUTH_TOKEN env var if None. Defaults to None.
        timeout (float, optional): Request timeout in seconds. Defaults to 120.0.
        raise_for_status (bool, optional): Whether to automatically raise MaestroApiError for non-2xx responses. Defaults to True.

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
        token: Optional[str] = None,
        timeout: float = 120.0,
        raise_for_status: bool = True,
    ):
        try:
            self.organization_id: UUID = UUID(str(organization_id))
        except (ValueError, TypeError):
             raise ValueError("organization_id must be a valid UUID or UUID string.")

        self.agent_id: Optional[UUID] = None
        if agent_id is not None:
             try:
                 self.agent_id = UUID(str(agent_id))
             except (ValueError, TypeError):
                 raise ValueError("agent_id must be a valid UUID or UUID string if provided.")

        resolved_base_url = base_url or os.getenv("MAESTRO_API_URL")
        if not resolved_base_url:
            resolved_base_url = "https://dantalabs.com"

        resolved_token = token or os.getenv("MAESTRO_AUTH_TOKEN")
        if not resolved_token:
            print("Warning: Maestro auth token not provided during initialization. Use set_token() before making API calls.")
            resolved_token = ""

        # Initialize HTTP client
        self.http = HTTPClient(resolved_base_url, resolved_token, timeout, raise_for_status)
        
        # Initialize resource managers
        self.organizations = OrganizationResource(self.http, self.organization_id)
        self.agents = AgentResource(self.http, self.organization_id)

    def set_token(self, token: str):
        """Sets or updates the authentication token."""
        if not token: 
            raise ValueError("Token cannot be empty.")
        self.http._token = token

    def clear_token(self):
        """Clears the current authentication token."""
        self.http._token = ""

    def _ensure_agent_id_set(self) -> UUID:
        """Checks if agent_id is set and returns it, otherwise raises ValueError."""
        if self.agent_id is None:
            raise ValueError("This method requires the client to be initialized with an agent_id, or agent_id passed explicitly.")
        return self.agent_id

    # Convenience methods that delegate to resources (backward compatibility)
    def create_organization(self, org_data):
        return self.organizations.create(org_data)
    
    def verify_token_with_email(self, email: str, token: str):
        return self.organizations.verify_token_with_email(email, token)
    
    def get_my_organizations(self):
        return self.organizations.list_my_organizations()
    
    def create_agent_definition(self, agent_definition_data):
        return self.agents.create_definition(agent_definition_data)
    
    def list_agent_definitions(self, name: Optional[str] = None):
        return self.agents.list_definitions(name)
    
    def get_agent_definition(self, definition_id: UUID):
        return self.agents.get_definition(definition_id)
    
    def update_agent_definition(self, definition_id: UUID, definition_data):
        return self.agents.update_definition(definition_id, definition_data)
    
    def create_agent(self, agent_data):
        return self.agents.create(agent_data)
    
    def list_agents(self, name: Optional[str] = None):
        return self.agents.list(name)
    
    def get_agent(self, agent_id: UUID):
        return self.agents.get(agent_id)
    
    def update_agent(self, agent_id: UUID, agent_data):
        return self.agents.update(agent_id, agent_data)

    def execute_agent_code_sync(self, variables, agent_id: Optional[UUID] = None, executor_type: Optional[str] = None):
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        return self.agents.execute_code_sync(variables, agent_id_to_use, executor_type)

    def health_check(self) -> bool:
        """Performs a health check on the Maestro API."""
        try:
            response = self.http.request(
                method="GET", path="/api/v1/utils/health-check/",
                expected_status=200, return_type="response", add_org_id_query=False,
            )
            if response.status_code == 200:
                try:
                    return response.json() is True
                except Exception:
                    return response.text.strip().lower() == 'true'
            else:
                return False
        except Exception:
            return False

    def close(self):
        """Closes the underlying HTTP client connection."""
        self.http.close()

    def __enter__(self):
        """Prepares the client when used in a 'with' statement."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensures the client is closed when exiting a 'with' block."""
        self.close()