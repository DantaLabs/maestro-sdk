import httpx
import io
import os
import collections.abc
import copy
from typing import Optional, Dict, Any, List, Union, Tuple, Iterator
from uuid import UUID, uuid4
from pydantic import EmailStr 

from .models import ( 
    MaestroBaseModel, Token, 
    Message,
    ValidationError, HTTPValidationError, OrganizationCreate, OrganizationRead, OrganizationUpdate,
    OrganizationMember, AgentDefinitionCreate, AgentDefinition, AgentCreate, Agent,
    NetworkGenerationRequest, NetworkResponse, NetworkListResponse, NetworkErrorResponse,
    AdapterCreate, AdapterUpdate, AdapterResponse, AdapterListResponse, CodeExecution, ReturnFile,
    MemoryUpdate, AgentUpdate
)
from .exceptions import (
    MaestroError, MaestroApiError, MaestroAuthError, MaestroValidationError
)
from .memory import ManagedMemory 


def _clean_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Removes keys with None values."""
    return {k: v for k, v in params.items() if v is not None}

class MaestroClient:
    """
    Python SDK Client for the Maestro API using Bearer Token Authentication.

    Args:
        organization_id (Union[UUID, str]): The UUID of the organization context for API calls.
        agent_id (Optional[Union[UUID, str]], optional): Default Agent ID for agent-specific calls. Defaults to None.
        base_url (Optional[str], optional): The base URL of the Maestro API. Reads from MAESTRO_API_URL env var if None. Defaults to None.
        token (Optional[str], optional): The Bearer token for authentication. Reads from MAESTRO_AUTH_TOKEN env var if None. Defaults to None.
        timeout (float, optional): Request timeout in seconds. Defaults to 30.0.
        raise_for_status (bool, optional): Whether to automatically raise MaestroApiError for non-2xx responses. Defaults to True.

    Raises:
        ValueError: If required parameters (organization_id, base_url, token) are missing or invalid.
        MaestroAuthError: If authentication fails during API calls.
        MaestroValidationError: If API calls result in a 422 validation error.
        MaestroApiError: For other non-2xx API errors if raise_for_status is True.
        MaestroError: For general SDK or unexpected errors.
    """
    def __init__(
        self,
        organization_id: Union[UUID, str],
        agent_id: Optional[Union[UUID, str]] = None,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        timeout: float = 30.0,
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
            #raise ValueError("Maestro API base URL must be provided via 'base_url' or MAESTRO_API_URL env var.")
            resolved_base_url = "https://dantalabs.com"
        self.base_url = resolved_base_url.rstrip("/")

        resolved_token = token or os.getenv("MAESTRO_AUTH_TOKEN")
        if not resolved_token:
            print("Warning: Maestro auth token not provided during initialization. Use set_token() before making API calls.")
            self._token = None
        else:
             self._token = resolved_token

        self._timeout = timeout
        self._raise_for_status = raise_for_status
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """Initializes or returns the httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(base_url=self.base_url, timeout=self._timeout)
        return self._client

    def _ensure_agent_id_set(self) -> UUID:
        """Checks if agent_id is set and returns it, otherwise raises ValueError."""
        if self.agent_id is None:
            raise ValueError("This method requires the client to be initialized with an agent_id, or agent_id passed explicitly.")
        return self.agent_id

    def _update_headers(self, headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Adds Authorization header if token exists."""
        final_headers = headers or {}
        final_headers.setdefault("Accept", "application/json")
        if not self._token:
            raise MaestroAuthError(401, "Authentication token is not set. Use set_token() or provide it during initialization.")
        final_headers["Authorization"] = f"Bearer {self._token}"
        return final_headers

    # --- Core Request Logic ---
    def _request(
        self,
        method: str,
        path: str,
        path_params: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        form_data: Optional[Dict[str, str]] = None,
        files: Optional[Dict[str, Tuple[str, io.BytesIO, str]]] = None,
        expected_status: int = 200,
        response_model: Optional[type[MaestroBaseModel]] = None,
        return_type: str = "json",
        *, 
        add_org_id_query: bool = True 
    ) -> Any:
        """
        Internal helper for making requests to the Maestro API.
        
        Automatically adds organization_id query param unless add_org_id_query=False.
        Handles authentication, serialization, and error handling for all API calls.
        """
        http_client = self._get_client() 

        url_path = path
        if path_params:
            try:
             
                str_path_params = {k: str(v) for k, v in path_params.items()}
                url_path = path.format(**str_path_params)
            except KeyError as e:
                raise ValueError(f"Missing path parameter: {e}") from e
            except Exception as e:
                 raise ValueError(f"Error formatting path '{path}' with params {path_params}: {e}") from e

        headers = self._update_headers() # This will raise MaestroAuthError if token is needed but missing
        content_to_send = None
        files_to_send = None
        
        request_query_params = query_params or {}

       
        if add_org_id_query:
             if self.organization_id is None:
                  raise ValueError("Organization ID is required for this request but not set.")
             request_query_params.setdefault('organization_id', str(self.organization_id))

        str_query_params = {}
        for k, v in request_query_params.items():
             if isinstance(v, bool): str_query_params[k] = str(v).lower() 
             elif isinstance(v, UUID): str_query_params[k] = str(v)
             elif v is not None: str_query_params[k] = str(v)

        final_query_params = _clean_params(str_query_params)

        
        current_json_data = json_data
        if current_json_data is not None:
            if isinstance(current_json_data, MaestroBaseModel):
                 content_to_send = current_json_data.model_dump(mode='json', exclude_unset=True, exclude_none=True)
            else:
                
                 def stringify_uuids(d):
                     if isinstance(d, dict): return {k: stringify_uuids(v) for k, v in d.items()}
                     if isinstance(d, list): return [stringify_uuids(i) for i in d]
                     if isinstance(d, UUID): return str(d)
                     return d
                 content_to_send = stringify_uuids(current_json_data)
            if not files and not form_data:
                 headers["Content-Type"] = "application/json"
        elif form_data:
            content_to_send = form_data
        elif files:
            files_to_send = files
            data_fields = final_query_params or {}
            if form_data:
                 data_fields.update(form_data)
            content_to_send = _clean_params(data_fields)
            final_query_params = None 

        try:
            response = http_client.request(
                method,
                url_path,
                params=final_query_params if not (files or (form_data and method != "GET")) else None,
                json=content_to_send if current_json_data is not None and not (form_data or files) else None,
                data=content_to_send if (form_data or files) else None,
                files=files_to_send,
                headers=headers,
            )

            if self._raise_for_status and not (200 <= response.status_code < 300):
                 error_detail: Any = None
                 try:
                     error_detail = response.json()
                 except Exception:
                     error_detail = response.text or f"Status Code {response.status_code}, No Body"

                 if response.status_code in (401, 403):
                     raise MaestroAuthError(response.status_code, error_detail)
                 elif response.status_code == 422:
                     raise MaestroValidationError(response.status_code, error_detail)
                 else:
                     # General API error for other non-2xx codes
                     raise MaestroApiError(response.status_code, error_detail)

            elif not (200 <= response.status_code < 300) and response.status_code != expected_status:
                 print(f"Warning: Received status code {response.status_code}, expected {expected_status}. raise_for_status is False.")

            elif response.status_code == 204:
                 if expected_status != 204:
                     print(f"Warning: Received 204 No Content, but expected status {expected_status}.")
                 return None

            if return_type == "none":
                return None
            if return_type == "json":
                try:
                    resp_json = response.json()
                except Exception as e:
                    raise MaestroError(f"Failed to decode JSON response (Status: {response.status_code}): {e}\nResponse Text: {response.text[:500]}...") from e

                if response_model:
                    try:
                        is_list_model = getattr(response_model, '__origin__', None) in (list, List)

                        if isinstance(resp_json, list) and is_list_model:
                             item_model = response_model.__args__[0]
                             # Validate each item in the list against the item model
                             return [item_model.model_validate(item) for item in resp_json]
                        elif not isinstance(resp_json, list) and not is_list_model:
                             # Validate the single JSON object against the model
                             return response_model.model_validate(resp_json)
                        elif isinstance(resp_json, dict) and is_list_model:
                            # Handle cases like ItemsPublic where the list is nested
                            return response_model.model_validate(resp_json)
                        else:
                             # Mismatch between JSON structure (list/dict) and expected model type (List/Single)
                             raise MaestroError(f"Response JSON type ({type(resp_json).__name__}) does not match expected model type ({response_model}). JSON: {str(resp_json)[:200]}...")
                    except Exception as e:
                        # Catch Pydantic validation errors or other parsing issues
                        raise MaestroError(f"Failed to parse response into {response_model}: {e}\nResponse JSON: {str(resp_json)[:500]}...") from e
                else:
                    # Return raw JSON if no model specified
                    return resp_json
            elif return_type == "text":
                return response.text
            elif return_type == "bytes":
                return response.content
            elif return_type == "response":
                # Return the raw httpx.Response object
                return response
            else:
                raise ValueError(f"Invalid return_type specified: {return_type}")

        except httpx.RequestError as e:
            # Errors during connection, timeout, etc.
            raise MaestroError(f"HTTP request failed: {e}") from e
        except MaestroError:
             raise # Re-raise Maestro specific errors directly
        except Exception as e:
             # Catch any other unexpected errors during request/response processing
             raise MaestroError(f"An unexpected error occurred during the request processing: {e}") from e


 
    def set_token(self, token: str):
        """Sets or updates the authentication token."""
        if not token: raise ValueError("Token cannot be empty.")
        self._token = token

    def clear_token(self):
        """Clears the current authentication token."""
        self._token = None


    
    # --- Organizations (Manage Organizations Themselves) ---
    def create_organization(self, org_data: OrganizationCreate) -> OrganizationRead:
        """
        Creates a new organization.
        
        Args:
            org_data: Organization creation data including name and other details
            
        Returns:
            OrganizationRead: The created organization details
        """
        return self._request(
            method="POST", path="/api/v1/organizations/", json_data=org_data,
            expected_status=200, response_model=OrganizationRead, add_org_id_query=False
        )

    def verify_token_with_email(self, email: str, token: str) -> Dict[str, Any]:
        """
        Verifies a token with an email address to retrieve an organization ID.
        
        Args:
            email: The email address registered with the token
            token: The token to verify
            
        Returns:
            Dict[str, Any]: Response containing organization ID
            
        Raises:
            MaestroAuthError: If authentication fails
            MaestroApiError: If API call fails
        """
        payload = {
            "email": email,
            "token": token
        }
        return self._request(
            method="POST", path="/api/v1/organizations/verify-token", 
            json_data=payload,
            expected_status=200, response_model=None, return_type="json", add_org_id_query=False
        )

    def get_my_organizations(self) -> List[OrganizationRead]:
        """
        Gets a list of organizations the current user is a member of.
        
        Returns:
            List[OrganizationRead]: List of organizations the authenticated user belongs to
        """
        return self._request(
            method="GET", path="/api/v1/organizations/",
            expected_status=200, response_model=List[OrganizationRead], add_org_id_query=False
        )

    # --- Organization Context Actions (Using Initialized self.organization_id) ---
    def update_organization(self, organization_update: OrganizationUpdate) -> OrganizationRead:
        """
        Updates the organization specified during client initialization.
        
        Args:
            organization_update: Organization update data including fields to change
            
        Returns:
            OrganizationRead: The updated organization details
            
        Raises:
            ValueError: If client was not initialized with an organization_id
        """
        if not self.organization_id: raise ValueError("Client must be initialized with an organization_id for this operation.")
        return self._request(
            method="PUT", path="/api/v1/organizations/{organization_id}",
            path_params={"organization_id": self.organization_id}, json_data=organization_update,
            expected_status=200, response_model=OrganizationRead
        )
    def delete_organization(self) -> None:
        """
        Deletes the organization specified during client initialization.
        
        Raises:
            ValueError: If client was not initialized with an organization_id
        """
        if not self.organization_id: raise ValueError("Client must be initialized with an organization_id for this operation.")
        return self._request(
            method="DELETE", path="/api/v1/organizations/{organization_id}",
            path_params={"organization_id": self.organization_id},
            expected_status=204, return_type="none"
        )
    def read_organization(self) -> OrganizationRead:
        """
        Reads the details of the organization specified during client initialization.
        
        Returns:
            OrganizationRead: Organization details
            
        Raises:
            ValueError: If client was not initialized with an organization_id
        """
        if not self.organization_id: raise ValueError("Client must be initialized with an organization_id for this operation.")
        return self._request(
            method="GET", path="/api/v1/organizations/{organization_id}",
            path_params={"organization_id": self.organization_id},
            expected_status=200, response_model=OrganizationRead
        )
    def get_organization_members(self) -> List[OrganizationMember]:
        """
        Gets members of the organization specified during client initialization.
        
        Returns:
            List[OrganizationMember]: List of organization members with their roles and details
            
        Raises:
            ValueError: If client was not initialized with an organization_id
        """
        if not self.organization_id: raise ValueError("Client must be initialized with an organization_id for this operation.")
        return self._request(
            method="GET", path="/api/v1/organizations/{organization_id}/members",
            path_params={"organization_id": self.organization_id},
            expected_status=200, response_model=List[OrganizationMember]
        )
    def generate_invitation_token(self, is_single_use: bool = True, expiration_days: int = 7) -> Dict[str, Any]:
        """
        Generates an invitation token for the current organization.
        
        Args:
            is_single_use: Whether the token can only be used once
            expiration_days: Number of days until token expires
            
        Returns:
            Dict[str, Any]: Token details including the token string and expiration
            
        Raises:
            ValueError: If client was not initialized with an organization_id
        """
        if not self.organization_id: raise ValueError("Client must be initialized with an organization_id for this operation.")
        params = {"is_single_use": is_single_use, "expiration_days": expiration_days}
        return self._request(
            method="POST", path="/api/v1/organizations/{organization_id}/invite",
            path_params={"organization_id": self.organization_id}, query_params=params,
            expected_status=200, response_model=None, return_type="json"
        )
    def join_organization(self, token: str) -> Dict[str, Any]:
        """
        Allows the current user to join an organization using an invitation token.
        
        Args:
            token: The invitation token string
            
        Returns:
            Dict[str, Any]: Response containing joined organization details
        """
        params = {"token": token}
        return self._request(
            method="POST", path="/api/v1/organizations/join-token", query_params=params,
            expected_status=200, response_model=None, return_type="json", add_org_id_query=False
        )
    def delete_user_from_organization(self, user_id: UUID) -> Dict[str, Any]:
        """
        Removes a user from the organization specified during client initialization.
        
        Args:
            user_id: UUID of the user to remove
            
        Returns:
            Dict[str, Any]: Response confirming removal
            
        Raises:
            ValueError: If client was not initialized with an organization_id
        """
        if not self.organization_id: raise ValueError("Client must be initialized with an organization_id for this operation.")
        return self._request(
            method="DELETE", path="/api/v1/organizations/{organization_id}/users/{user_id}",
            path_params={"organization_id": self.organization_id, "user_id": user_id},
            expected_status=200, response_model=None, return_type="json"
        )


    # --- Agents (Scoped to Initialized self.organization_id) ---
    def create_agent_definition(self, agent_definition_data: AgentDefinitionCreate) -> AgentDefinition:
        """
        Creates an agent definition within the current organization.
        
        Args:
            agent_definition_data: Definition creation data including name, description, and configuration
            
        Returns:
            AgentDefinition: The created agent definition
        """
        # Convert the Pydantic model to a dict first before nesting
        payload = {"agent_definition_data": agent_definition_data.model_dump(mode='json', exclude_unset=True, exclude_none=True)}
        return self._request(
            method="POST", path="/api/v1/agents/agent-definitions/", json_data=payload,
            expected_status=200, response_model=AgentDefinition
        )
        
    def list_agent_definitions(self, name: Optional[str] = None) -> List[AgentDefinition]:
        """
        Lists agent definitions within the current organization.
        
        Args:
            name: Optional filter to find definitions by name
            
        Returns:
            List[AgentDefinition]: List of agent definitions
        """
        query = {}
        if name:
            query["name"] = name
        return self._request(
            method="GET", path="/api/v1/agents/agent-definitions/",
            query_params=query if query else None,
            expected_status=200, response_model=List[AgentDefinition]
        )
        
    def get_agent_definition(self, definition_id: UUID) -> AgentDefinition:
        """
        Gets a specific agent definition by ID within the current organization.
        
        Args:
            definition_id: UUID of the agent definition
            
        Returns:
            AgentDefinition: The requested agent definition
        """
        return self._request(
            method="GET", path="/api/v1/agents/agent-definitions/{definition_id}",
            path_params={"definition_id": definition_id},
            expected_status=200, response_model=AgentDefinition
        )
        
    def update_agent_definition(self, definition_id: UUID, definition_data: AgentDefinitionCreate) -> AgentDefinition:
        """
        Updates an existing Agent Definition.
        
        Args:
            definition_id: UUID of the agent definition to update
            definition_data: Updated definition data
            
        Returns:
            AgentDefinition: The updated agent definition
        """
        # Convert the Pydantic model to a dict first before nesting
        payload = {"update_data": definition_data.model_dump(mode='json')}
        return self._request(
            method="PUT",
            path="/api/v1/agents/agent-definitions/{definition_id}",
            path_params={"definition_id": definition_id},
            json_data=payload,
            expected_status=200,
            response_model=AgentDefinition
        )

    # Agent instance methods
    
    def create_agent(self, agent_data: AgentCreate) -> Agent:
        """
        Creates an agent within the current organization.
        
        Args:
            agent_data: Agent creation data including agent_definition_id and other configuration
            
        Returns:
            Agent: The created agent
        """
        payload = {"agent_data": agent_data.model_dump(mode='json', exclude_unset=True, exclude_none=True)}
        return self._request(
            method="POST", path="/api/v1/agents/", json_data=payload,
            expected_status=200, response_model=Agent
        )
        
    def list_agents(self, name: Optional[str] = None) -> List[Agent]:
        """
        Lists agents within the current organization.
        
        Args:
            name: Optional filter to find agents by name
            
        Returns:
            List[Agent]: List of agents
        """
        query = {}
        if name:
            query["name"] = name
        return self._request(
            method="GET", path="/api/v1/agents/",
            query_params=query if query else None,
            expected_status=200, response_model=List[Agent]
        )
        
    def get_agent(self, agent_id: UUID) -> Agent:
        """
        Gets a specific agent by ID within the current organization.
        
        Args:
            agent_id: UUID of the agent
            
        Returns:
            Agent: The requested agent
        """
        return self._request(
            method="GET", path="/api/v1/agents/{agent_id}", path_params={"agent_id": agent_id},
            expected_status=200, response_model=Agent
        )
        
    def update_agent(self, agent_id: UUID, agent_data: AgentUpdate) -> Agent:
        """
        Updates an existing Agent.
        
        Args:
            agent_id: UUID of the agent to update
            agent_data: AgentUpdate model containing fields to update
            
        Returns:
            Agent: The updated agent
        """
        payload = {"update_data": agent_data.model_dump(mode='json')}
        return self._request(
            method="PUT",
            path="/api/v1/agents/{agent_id}",
            path_params={"agent_id": agent_id},
            json_data=payload,
            expected_status=200,
            response_model=Agent
        )
    
    # Agent execution methods

    def execute_agent_code(self, input_variables: Dict[str, Any], agent_id: Optional[UUID] = None, executor_type: Optional[str] = None) -> CodeExecution:
        """
        Executes the code associated with an agent.

        Args:
            input_variables: Input data for the execution
            agent_id: The agent to execute (if None, uses the agent_id set during client initialization)
            executor_type: Specific executor type if needed

        Returns:
            CodeExecution: Details of the execution result

        Raises:
            ValueError: If agent_id is not provided and not set during client init
        """
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        query = {}
        if executor_type: query["executor_type"] = executor_type
        payload = {"input_variables": input_variables }
        return self._request(
            method="POST", path="/api/v1/agents/run/{agent_id}/execute",
            path_params={"agent_id": agent_id_to_use},
            query_params=query if query else None,
            json_data=payload,
            expected_status=200
        )

    def execute_agent_code_sync(self, variables: Dict[str, Any], agent_id: Optional[UUID] = None, executor_type: Optional[str] = None) -> CodeExecution:
        """
        Executes the code associated with an agent synchronously.

        Args:
            variables: Input variables for the execution
            agent_id: The agent to execute (if None, uses the agent_id set during client initialization)
            executor_type: Specific executor type if needed

        Returns:
            CodeExecution: Details of the execution result

        Raises:
            ValueError: If agent_id is not provided and not set during client init
        """
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        query = {}
        if executor_type: query["executor_type"] = executor_type
        payload = {"input_variables":{"variables":variables}}
        return self._request(
            method="POST", path="/api/v1/agents/run/{agent_id}/execute-sync",
            path_params={"agent_id": agent_id_to_use},
            query_params=query if query else None,
            json_data=payload,
            expected_status=200
        )

    def get_execution_status(self, execution_id: UUID) -> CodeExecution:
        """
        Gets the status of a specific code execution within the organization.
        
        Args:
            execution_id: UUID of the execution
            
        Returns:
            CodeExecution: Execution details and status
        """
        return self._request(
            method="GET", path="/api/v1/agents/executions/{execution_id}",
            path_params={"execution_id": execution_id},
            expected_status=200
        )
        
    def list_executions(self, limit: int = 10, skip: int = 0) -> List[CodeExecution]:
        """
        Lists code executions within the current organization.
        
        Args:
            limit: Maximum number of executions to return
            skip: Number of executions to skip (for pagination)
            
        Returns:
            List[CodeExecution]: List of code executions
        """
        query = {"limit": limit, "skip": skip}
        return self._request(
            method="GET", path="/api/v1/agents/executions", query_params=query,
            expected_status=200, response_model=List[CodeExecution]
        )


    # --- Networks (Scoped to Initialized self.organization_id) ---
    def generate_network(self, request: NetworkGenerationRequest) -> NetworkResponse:
        """
        Generates a network based on a prompt within the current organization.
        
        Args:
            request: Network generation request containing the prompt and parameters
            
        Returns:
            NetworkResponse: The generated network details
        """
        payload = request
        return self._request(
            method="POST", path="/api/v1/networks/generate/", json_data=payload,
            expected_status=200, response_model=NetworkResponse
        )
    
    def list_networks(self, skip: int = 0, limit: int = 100) -> NetworkListResponse:
        """
        Lists networks within the current organization.
        
        Args:
            skip: Number of networks to skip (for pagination)
            limit: Maximum number of networks to return
            
        Returns:
            NetworkListResponse: List of networks with pagination details
        """
        query = {"skip": skip, "limit": limit}
        return self._request(
            method="GET", path="/api/v1/networks/", query_params=query,
            expected_status=200, response_model=NetworkListResponse
        )
    
    def get_network(self, network_id: UUID) -> NetworkResponse:
        """
        Gets a specific network by ID within the current organization.
        
        Args:
            network_id: UUID of the network
            
        Returns:
            NetworkResponse: The requested network details
        """
        return self._request(
            method="GET", path="/api/v1/networks/{network_id}", path_params={"network_id": network_id},
            expected_status=200, response_model=NetworkResponse
        )
    
    def delete_network(self, network_id: UUID) -> None:
        """
        Deletes a specific network by ID within the current organization.
        
        Args:
            network_id: UUID of the network to delete
        """
        return self._request(
            method="DELETE", path="/api/v1/networks/{network_id}", path_params={"network_id": network_id},
            expected_status=204, return_type="none"
        )

    # --- Adapters (Scoped to Initialized self.organization_id) ---
    def create_adapter(self, adapter_data: AdapterCreate) -> AdapterResponse:
        """
        Creates an adapter within the current organization.
        
        Args:
            adapter_data: Adapter creation data
            
        Returns:
            AdapterResponse: The created adapter details
        """
        payload = adapter_data
        return self._request(
            method="POST", path="/api/v1/adapters/", json_data=payload,
            expected_status=200, response_model=AdapterResponse
        )
    
    def list_adapters(self, skip: int = 0, limit: int = 100) -> AdapterListResponse:
         """
         Lists adapters within the current organization.
         
         Args:
             skip: Number of adapters to skip (for pagination)
             limit: Maximum number of adapters to return
             
         Returns:
             AdapterListResponse: List of adapters with pagination details
         """
         query = {"skip": skip, "limit": limit}
         return self._request(
             method="GET", path="/api/v1/adapters/", query_params=query,
             expected_status=200, response_model=AdapterListResponse
         )
    
    def get_adapter(self, adapter_id: UUID) -> AdapterResponse:
        """
        Gets a specific adapter by ID within the current organization.
        
        Args:
            adapter_id: UUID of the adapter
            
        Returns:
            AdapterResponse: The requested adapter details
        """
        return self._request(
            method="GET", path="/api/v1/adapters/{adapter_id}", path_params={"adapter_id": adapter_id},
            expected_status=200, response_model=AdapterResponse
        )
    
    def update_adapter(self, adapter_id: UUID, update_data: AdapterUpdate) -> AdapterResponse:
         """
         Updates a specific adapter by ID within the current organization.
         
         Args:
             adapter_id: UUID of the adapter to update
             update_data: Adapter update data
             
         Returns:
             AdapterResponse: The updated adapter details
         """
         return self._request(
             method="PUT", path="/api/v1/adapters/{adapter_id}", path_params={"adapter_id": adapter_id},
             json_data=update_data, expected_status=200, response_model=AdapterResponse
         )
    
    def delete_adapter(self, adapter_id: UUID) -> None:
         """
         Deletes a specific adapter by ID within the current organization.
         
         Args:
             adapter_id: UUID of the adapter to delete
         """
         return self._request(
             method="DELETE", path="/api/v1/adapters/{adapter_id}", path_params={"adapter_id": adapter_id},
             expected_status=204, return_type="none"
         )

    # Memory Management methods
    
    def get_managed_memory(self, memory_name: str, agent_id: Optional[UUID] = None, **kwargs) -> ManagedMemory:
        """
        Gets a ManagedMemory instance for interacting with a specific agent's memory.

        Args:
            memory_name: The name of the memory
            agent_id: The agent context (if None, uses the agent_id set during client initialization)
            **kwargs: Additional arguments passed to the ManagedMemory constructor
                      (e.g., auto_load, create_if_missing)

        Returns:
            ManagedMemory: An object to interact with the specified memory

        Raises:
            ValueError: If agent_id is not provided and not set during client init
        """
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        return ManagedMemory(client=self, agent_id=agent_id_to_use, memory_name=memory_name, **kwargs)

    def add_memory_to_agent(self, memory_data: dict, agent_id: Optional[UUID] = None) -> Dict[str, Any]:
        """
        Adds a new memory record and associates it with an agent.

        Args:
            memory_data: Dictionary containing memory details (name, data, type, etc.)
            agent_id: The agent to associate with (if None, uses the agent_id set during client initialization)

        Returns:
            Dict[str, Any]: The created memory details as returned by the API

        Raises:
            ValueError: If agent_id is not provided and not set during client init
        """
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        return self._request(
            method="POST", path="/api/v1/agents/{agent_id}/memories/",
            path_params={"agent_id": agent_id_to_use},
            json_data=memory_data,
            expected_status=200, response_model=None, return_type="json"
        )

    def get_agent_memories(self, agent_id: Optional[UUID] = None) -> List[Dict[str, Any]]:
        """
        Gets a list of memories associated with a specific agent.

        Args:
            agent_id: The agent ID (if None, uses the agent_id set during client initialization)

        Returns:
            List[Dict[str, Any]]: A list of memory details dictionaries

        Raises:
            ValueError: If agent_id is not provided and not set during client init
        """
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        return self._request(
            method="GET", path="/api/v1/agents/{agent_id}/memories/",
            path_params={"agent_id": agent_id_to_use},
            expected_status=200, response_model=None, return_type="json"
        )

    def _get_memory_by_name_raw(self, memory_name: str, agent_id: Optional[UUID] = None) -> Optional[Dict[str, Any]]:
        """
        Internal helper to fetch raw memory data by name for a specific agent.
        Handles 404 by returning None.

        Args:
            memory_name: The name of the memory
            agent_id: The agent ID (if None, uses the agent_id set during client initialization)
            
        Returns:
            Optional[Dict[str, Any]]: Raw memory data dict or None if not found
            
        Raises:
            MaestroApiError: For non-404 errors
            ValueError: If agent_id is not provided and not set during client init
        """
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        try:
            return self._request(
                method="GET", path="/api/v1/agents/{agent_id}/memories/by-name/{memory_name}",
                path_params={"agent_id": agent_id_to_use, "memory_name": memory_name},
                expected_status=200, response_model=None, return_type="json",
            )
        except MaestroApiError as e:
            if e.status_code == 404:
                return None # Memory not found
            print(f"API Error fetching memory by name '{memory_name}': Status {e.status_code}, Detail: {e.error_detail}")
            raise
        except Exception as e:
             print(f"Unexpected error fetching memory by name '{memory_name}': {e}")
             raise

    def get_memory(self, memory_id: UUID) -> Dict[str, Any]:
        """
        Gets details of a specific memory by its ID.

        Args:
            memory_id: The UUID of the memory

        Returns:
            Dict[str, Any]: The memory details dictionary
        """
        return self._request(
            method="GET", path="/api/v1/agents/memories/{memory_id}", path_params={"memory_id": memory_id},
            expected_status=200, response_model=None, return_type="json"
        )

    def update_memory(self, memory_id: UUID, update_data: dict, agent_id: Optional[UUID] = None) -> Dict[str, Any]:
        """
        Update an existing memory record.

        Args:
            memory_id: The UUID of the memory to update
            update_data: A dictionary containing fields to update, should include 'update_strategy' field
                         with value 'merge' or 'replace'
            agent_id: Agent context if required by the specific update logic (optional)

        Returns:
            Dict[str, Any]: The updated memory data as returned by the API

        Raises:
            MaestroApiError: If the API request fails, including validation errors (422)
            MaestroValidationError: If update_strategy field is missing or invalid
        """
        query_params = {}
        if agent_id:
            query_params["agent_id"] = str(agent_id)

        json_payload = update_data

        try:
            return self._request(
                method="PUT",
                path="/api/v1/agents/memories/{memory_id}",
                path_params={"memory_id": memory_id},
                query_params=query_params if query_params else None,
                json_data=json_payload,
                expected_status=200,
                response_model=None,
                return_type="json"
            )
        except MaestroValidationError as e:
            detail = str(e.error_detail) if e.error_detail else "Unknown validation error"
            error_msg = f"Memory update API validation error (422): {detail}"
            if "update_strategy" in detail and "Field required" in detail:
                 error_msg += "\nHint: 'update_strategy' ('merge' or 'replace') might be required by the API."
            if "data" in detail and "value is not a valid dict" in detail:
                 error_msg += "\nHint: Ensure the 'data' field in your update_data is a valid dictionary."
            print(error_msg)
            raise
        except MaestroApiError as e:
            print(f"API Error updating memory {memory_id}: Status {e.status_code}, Detail: {e.error_detail}")
            raise
        except Exception as e:
             print(f"Unexpected error updating memory {memory_id}: {e}")
             raise


    def delete_memory(self, memory_id: UUID) -> None:
        """
        Deletes a memory record by its ID.

        Args:
            memory_id: The UUID of the memory to delete
        """
        return self._request(
            method="DELETE", path="/api/v1/agents/memories/{memory_id}", path_params={"memory_id": memory_id},
            expected_status=204, return_type="none"
        )

    def disconnect_memory_from_agent(self, memory_id: UUID, agent_id: Optional[UUID] = None) -> None:
        """
        Disconnects a memory from an agent without deleting the memory itself.

        Args:
            memory_id: The UUID of the memory to disconnect
            agent_id: The agent to disconnect from (if None, uses the agent_id set during client initialization)
            
        Raises:
            ValueError: If agent_id is not provided and not set during client init
        """
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        return self._request(
            method="POST",
            path="/api/v1/agents/{agent_id}/disconnect-memory/{memory_id}",
            path_params={"agent_id": agent_id_to_use, "memory_id": memory_id},
            expected_status=204, return_type="none"
        )


    # File operations
    
    def upload_file(self, file: io.BytesIO, filename: str, content_type: str,
        project_id: Optional[Union[UUID, str]] = None, task_id: Optional[Union[UUID, str]] = None,
        chat_id: Optional[Union[UUID, str]] = None,) -> ReturnFile:
        """
        Upload a file associated with the client's organization.

        Args:
            file: The file content as bytes
            filename: The name of the file
            content_type: The MIME type of the file (e.g., 'text/plain', 'image/jpeg')
            project_id: Optional associated project ID
            task_id: Optional associated task ID
            chat_id: Optional associated chat ID

        Returns:
            ReturnFile: Metadata about the uploaded file
        """
        form_data_fields = {
            "project_id": str(project_id) if project_id else None,
            "task_id": str(task_id) if task_id else None,
            "chat_id": str(chat_id) if chat_id else None,
        }
        files_data = {"uploaded_file": (filename, file, content_type)}

        return self._request(
            method="POST", path="/api/v1/files/upload/",
            form_data=_clean_params(form_data_fields),
            files=files_data,
            expected_status=200, response_model=ReturnFile,
            add_org_id_query=True
        )

    # Utility methods
    
    def health_check(self) -> bool:
        """
        Performs a health check on the Maestro API.
        
        Returns:
            bool: True if the API is healthy, False otherwise
        """
        try:
            response = self._request(
                method="GET", path="/api/v1/utils/health-check/",
                expected_status=200, return_type="response", add_org_id_query=False,
            )
            if response.status_code == 200:
                try:
                    return response.json() is True
                except Exception:
                    return response.text.strip().lower() == 'true'
            else:
                print(f"Health check returned non-200 status: {response.status_code}")
                return False
        except MaestroApiError as e:
             print(f"Health check failed with API error: {e}")
             return False
        except httpx.RequestError as e:
             print(f"Health check failed with connection error: {e}")
             return False
        except MaestroError as e:
             print(f"Health check failed: {e}")
             return False
        except Exception as e:
             print(f"Health check encountered unexpected error: {e}")
             return False

    def test_email(self, email_to: EmailStr) -> Message:
        """
        Sends a test email via the Maestro service.
        
        Args:
            email_to: Email address to send test message to
            
        Returns:
            Message: Response containing email delivery status
        """
        params = {"email_to": email_to}
        return self._request(
            method="POST", path="/api/v1/utils/test-email/", query_params=params,
            expected_status=201,
            response_model=Message, add_org_id_query=False
        )
    
    # Lifecycle methods
    
    def close(self):
        """Closes the underlying HTTP client connection."""
        if hasattr(self, '_client') and self._client and not self._client.is_closed:
            self._client.close()

    def __enter__(self):
        """Prepares the client when used in a 'with' statement."""
        self._get_client()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Ensures the client is closed when exiting a 'with' block."""
        self.close()