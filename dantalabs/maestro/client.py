import httpx
import io
import os
import collections.abc
import copy
from typing import Optional, Dict, Any, List, Union, Tuple, Iterator
from uuid import UUID, uuid4
from pydantic import EmailStr 
from pathlib import Path

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

    def _get_client_with_timeout(self, timeout: float) -> httpx.Client:
        """Returns a httpx client with a custom timeout for specific operations."""
        return httpx.Client(base_url=self.base_url, timeout=timeout)

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
        files: Optional[Dict[str, Tuple[str, Any, str]]] = None,
        expected_status: int = 200,
        response_model: Optional[type[MaestroBaseModel]] = None,
        return_type: str = "json",
        *, 
        add_org_id_query: bool = True,
        custom_timeout: Optional[float] = None
    ) -> Any:
        """
        Internal helper for making requests to the Maestro API.
        
        Automatically adds organization_id query param unless add_org_id_query=False.
        Handles authentication, serialization, and error handling for all API calls.
        """
        # Use custom timeout client if specified, otherwise use default client
        if custom_timeout:
            http_client = self._get_client_with_timeout(custom_timeout)
            use_custom_client = True
        else:
            http_client = self._get_client()
            use_custom_client = False

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
            # For file uploads with embedded form fields, don't send separate data
            content_to_send = None

        try:
            response = http_client.request(
                method,
                url_path,
                params=final_query_params if files or (not form_data) else None,
                json=content_to_send if current_json_data is not None and not (form_data or files) else None,
                data=content_to_send if form_data and not files else None,  # Don't send data when we have files
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
        finally:
            # Clean up custom client if used
            if use_custom_client and http_client and not http_client.is_closed:
                http_client.close()


 
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

    # Bundle-related methods
    
    def create_bundle(
        self, 
        source_dir: str, 
        output_path: Optional[str] = None,
        include_requirements: bool = True,
        install_dependencies: bool = True,
        maestro_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Creates a ZIP bundle from a source directory for agent deployment.
        
        Args:
            source_dir: Path to the directory containing agent code
            output_path: Path for the output ZIP file. If None, creates in temp directory
            include_requirements: Whether to automatically include requirements from pyproject.toml or requirements.txt
            install_dependencies: Whether to install dependencies into the bundle (includes them as Python libraries)
            maestro_config: Optional maestro.yaml configuration to include in the bundle
            
        Returns:
            str: Path to the created bundle ZIP file
            
        Raises:
            MaestroError: If bundle creation fails
        """
        import zipfile
        import tempfile
        import os
        import yaml
        import subprocess
        import sys
        from pathlib import Path
        from subprocess import TimeoutExpired
        
        source_path = Path(source_dir)
        if not source_path.exists() or not source_path.is_dir():
            raise MaestroError(f"Source directory '{source_dir}' does not exist or is not a directory")
        
        # Create output path if not provided
        if output_path is None:
            temp_dir = tempfile.mkdtemp(prefix="maestro_bundle_")
            output_path = os.path.join(temp_dir, "agent_bundle.zip")
        
        # Create a temporary directory for dependency installation if needed
        deps_temp_dir = None
        if install_dependencies:
            deps_temp_dir = tempfile.mkdtemp(prefix="maestro_deps_")
        
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Keep track of files we've added to avoid duplicates
                added_files = set()
                
                # Add all files from source directory
                for root, dirs, files in os.walk(source_path):
                    # Skip common directories that shouldn't be in bundles
                    dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', '.pytest_cache', 'node_modules', '.venv', 'venv'}]
                    
                    for file in files:
                        # Skip common files that shouldn't be in bundles
                        if file.startswith('.') and file not in {'.env.example'}:
                            continue
                        if file.endswith(('.pyc', '.pyo', '.pyd')):
                            continue
                            
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, source_path)
                        zipf.write(file_path, arcname)
                        added_files.add(arcname)
                
                # Handle dependencies installation and inclusion
                if install_dependencies and deps_temp_dir:
                    requirements_content = self._extract_requirements(source_path)
                    if requirements_content:
                        # Create a temporary requirements file
                        req_file = os.path.join(deps_temp_dir, "temp_requirements.txt")
                        with open(req_file, 'w') as f:
                            f.write(requirements_content)
                        
                        try:
                            # Install dependencies to the temporary directory
                            print(f"Installing dependencies to bundle... (this may take several minutes)")
                            print(f"Installing from: {req_file}")
                            
                            result = subprocess.run([
                                sys.executable, "-m", "pip", "install", 
                                "-r", req_file,
                                "--target", deps_temp_dir,
                                "--upgrade",  # Ensure we get the latest compatible versions
                                "--no-cache-dir"  # Avoid cache issues
                            ], check=True, capture_output=True, text=True, timeout=900)  # 15 minute timeout
                            
                            if result.stdout:
                                print(f"Dependency installation completed.")
                            if result.stderr and result.returncode == 0:
                                print(f"Installation warnings: {result.stderr}")
                            
                            # Add installed packages to the bundle
                            package_count = 0
                            for root, dirs, files in os.walk(deps_temp_dir):
                                # Skip pip metadata directories but keep the actual packages
                                dirs[:] = [d for d in dirs if not d.endswith('.dist-info') and not d.endswith('.egg-info') and d != '__pycache__']
                                
                                for file in files:
                                    if file == "temp_requirements.txt":
                                        continue
                                    if file.endswith(('.pyc', '.pyo', '.pyd')):
                                        continue
                                        
                                    file_path = os.path.join(root, file)
                                    # Create archive path relative to deps_temp_dir
                                    arcname = os.path.relpath(file_path, deps_temp_dir)
                                    
                                    # Skip if file already exists in bundle (source takes precedence)
                                    if arcname not in added_files:
                                        zipf.write(file_path, arcname)
                                        added_files.add(arcname)
                                        package_count += 1
                            
                            print(f"Dependencies installed and included in bundle ({package_count} files added).")
                            
                        except subprocess.TimeoutExpired:
                            print(f"Warning: Dependency installation timed out after 15 minutes.")
                            print("Continuing with requirements.txt inclusion instead...")
                            
                            # Fall back to including requirements.txt if installation times out
                            if include_requirements and "requirements.txt" not in added_files:
                                zipf.writestr("requirements.txt", requirements_content)
                                added_files.add("requirements.txt")
                        except subprocess.CalledProcessError as e:
                            print(f"Warning: Failed to install dependencies (exit code {e.returncode}): {e}")
                            if e.stdout:
                                print(f"stdout: {e.stdout}")
                            if e.stderr:
                                print(f"stderr: {e.stderr}")
                            print("Continuing with requirements.txt inclusion instead...")
                            
                            # Fall back to including requirements.txt if installation fails
                            if include_requirements and "requirements.txt" not in added_files:
                                zipf.writestr("requirements.txt", requirements_content)
                                added_files.add("requirements.txt")
                        except Exception as e:
                            print(f"Warning: Unexpected error during dependency installation: {e}")
                            print("Continuing with requirements.txt inclusion instead...")
                            
                            # Fall back to including requirements.txt if installation fails
                            if include_requirements and "requirements.txt" not in added_files:
                                zipf.writestr("requirements.txt", requirements_content)
                                added_files.add("requirements.txt")
                
                # Handle requirements inclusion (only if not installing dependencies or if no dependencies found)
                elif include_requirements and "requirements.txt" not in added_files:
                    requirements_content = self._extract_requirements(source_path)
                    if requirements_content:
                        zipf.writestr("requirements.txt", requirements_content)
                        added_files.add("requirements.txt")
                
                # Create maestro.yaml config if provided (only if not already present)
                has_maestro_config = any(name in added_files for name in ["maestro.yaml", "maestro.yml"])
                
                if maestro_config and not has_maestro_config:
                    yaml_content = yaml.dump(maestro_config, default_flow_style=False)
                    zipf.writestr("maestro.yaml", yaml_content)
                    added_files.add("maestro.yaml")
                elif not has_maestro_config:
                    # Create a basic maestro.yaml if none exists
                    default_config = {
                        "entrypoint": "main.py",
                        "description": "Agent bundle",
                        "version": "1.0.0"
                    }
                    yaml_content = yaml.dump(default_config, default_flow_style=False)
                    zipf.writestr("maestro.yaml", yaml_content)
                    added_files.add("maestro.yaml")
                    
            return output_path
            
        except Exception as e:
            if output_path and os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except:
                    pass
            raise MaestroError(f"Failed to create bundle: {e}") from e
        finally:
            # Clean up temporary dependency directory
            if deps_temp_dir and os.path.exists(deps_temp_dir):
                try:
                    import shutil
                    shutil.rmtree(deps_temp_dir)
                except Exception:
                    pass  # Ignore cleanup errors
    
    def _extract_requirements(self, source_path: Path) -> Optional[str]:
        """
        Extracts requirements from pyproject.toml or requirements.txt files.
        
        Args:
            source_path: Path to the source directory
            
        Returns:
            Optional[str]: Requirements content or None if no requirements found
        """
        # Check for pyproject.toml first
        pyproject_path = source_path / "pyproject.toml"
        if pyproject_path.exists():
            pyproject_data = None
            
            # Try different TOML parsers
            try:
                import tomli
                with open(pyproject_path, 'rb') as f:
                    pyproject_data = tomli.load(f)
            except ImportError:
                try:
                    import tomllib
                    with open(pyproject_path, 'rb') as f:
                        pyproject_data = tomllib.load(f)
                except ImportError:
                    try:
                        import toml
                        with open(pyproject_path, 'r') as f:
                            pyproject_data = toml.load(f)
                    except ImportError:
                        pass  # No TOML parser available
            except Exception:
                pass  # Failed to parse pyproject.toml
                
            if pyproject_data:
                dependencies = []
                
                # Extract from project.dependencies
                if 'project' in pyproject_data and 'dependencies' in pyproject_data['project']:
                    dependencies.extend(pyproject_data['project']['dependencies'])
                
                # Extract from tool.poetry.dependencies (if using Poetry)
                if 'tool' in pyproject_data and 'poetry' in pyproject_data['tool']:
                    poetry_deps = pyproject_data['tool']['poetry'].get('dependencies', {})
                    for dep, version in poetry_deps.items():
                        if dep != 'python':  # Skip python version
                            if isinstance(version, str):
                                dependencies.append(f"{dep}{version}")
                            elif isinstance(version, dict) and 'version' in version:
                                dependencies.append(f"{dep}{version['version']}")
                            else:
                                dependencies.append(dep)
                
                if dependencies:
                    return '\n'.join(dependencies)
        
        # Check for requirements.txt
        requirements_path = source_path / "requirements.txt"
        if requirements_path.exists():
            try:
                return requirements_path.read_text().strip()
            except Exception:
                pass
        
        return None
    
    def upload_agent_bundle(
        self,
        bundle_path: str,
        name: str,
        description: Optional[str] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        interface_id: Optional[UUID] = None,
        entrypoint: str = "main.py",
        version: str = "1.0.0",
        requirements: Optional[List[str]] = None,
        additional_metadata: Optional[Dict[str, Any]] = None,
        shareable: bool = False,
        upload_timeout: float = 600.0
    ) -> AgentDefinition:
        """
        Uploads a ZIP bundle to create a new Agent Definition.
        
        Args:
            bundle_path: Path to the ZIP bundle file
            name: Name for the Agent Definition
            description: Optional description
            input_schema: Optional input schema
            output_schema: Optional output schema
            interface_id: Optional interface ID
            entrypoint: Main entry point file for the bundle (default: "main.py")
            version: Version of the bundle (default: "1.0.0")
            requirements: Optional list of requirements
            additional_metadata: Optional additional metadata dictionary
            shareable: Whether the agent definition is shareable (default: False)
            upload_timeout: Timeout in seconds for the upload operation (default: 600.0)
            
        Returns:
            AgentDefinition: The created agent definition
            
        Raises:
            MaestroError: If bundle upload fails
        """
        from pathlib import Path
        import json
        
        bundle_file = Path(bundle_path)
        if not bundle_file.exists() or not bundle_file.is_file():
            raise MaestroError(f"Bundle file '{bundle_path}' does not exist or is not a file")
        
        if not bundle_file.name.lower().endswith('.zip'):
            raise MaestroError("Bundle file must be a ZIP file")
        
        try:
            # Prepare form data for text fields
            form_data = {
                "name": name,
                "entrypoint": entrypoint,
                "version": version,
                "shareable": str(shareable).lower(),
            }
            
            if description:
                form_data["description"] = description
            if input_schema:
                form_data["input_schema"] = json.dumps(input_schema)
            if output_schema:
                form_data["output_schema"] = json.dumps(output_schema)
            if interface_id:
                form_data["interface_id"] = str(interface_id)
            if requirements:
                form_data["requirements"] = json.dumps(requirements)
            if additional_metadata:
                form_data["additional_metadata"] = json.dumps(additional_metadata)
            
            # Prepare file data for the bundle - keep file open during request
            with open(bundle_file, 'rb') as bundle_file_handle:
                # Include both files and form fields in the files parameter for proper multipart form
                files_data = {
                    "bundle": (bundle_file.name, bundle_file_handle, "application/zip"),
                }
                
                # Add form fields to files_data (httpx format for form fields in multipart)
                for key, value in form_data.items():
                    files_data[key] = (None, value)
                
                return self._request(
                    method="POST",
                    path="/api/v1/agents/agent-definitions/bundle/",
                    files=files_data,  # Only use files parameter, no separate form_data
                    expected_status=200,
                    response_model=AgentDefinition,
                    custom_timeout=upload_timeout
                )
            
        except Exception as e:
            if isinstance(e, (MaestroError, MaestroApiError)):
                raise
            raise MaestroError(f"Failed to upload bundle: {e}") from e
    
    def update_agent_bundle(
        self,
        definition_id: UUID,
        bundle_path: str,
        entrypoint: Optional[str] = None,
        version: Optional[str] = None,
        requirements: Optional[List[str]] = None,
        additional_metadata: Optional[Dict[str, Any]] = None,
        upload_timeout: float = 600.0
    ) -> AgentDefinition:
        """
        Updates an existing bundled Agent Definition with a new ZIP bundle.
        
        Args:
            definition_id: UUID of the agent definition to update
            bundle_path: Path to the new ZIP bundle file
            entrypoint: Optional main entry point file for the bundle
            version: Optional version of the bundle
            requirements: Optional list of requirements
            additional_metadata: Optional additional metadata dictionary
            upload_timeout: Timeout in seconds for the upload operation (default: 600.0)
            
        Returns:
            AgentDefinition: The updated agent definition
            
        Raises:
            MaestroError: If bundle update fails
        """
        from pathlib import Path
        import json
        
        bundle_file = Path(bundle_path)
        if not bundle_file.exists() or not bundle_file.is_file():
            raise MaestroError(f"Bundle file '{bundle_path}' does not exist or is not a file")
        
        if not bundle_file.name.lower().endswith('.zip'):
            raise MaestroError("Bundle file must be a ZIP file")
        
        try:
            # Prepare form data for optional metadata fields
            form_data = {}
            
            if entrypoint:
                form_data["entrypoint"] = entrypoint
            if version:
                form_data["version"] = version
            if requirements:
                form_data["requirements"] = json.dumps(requirements)
            if additional_metadata:
                form_data["additional_metadata"] = json.dumps(additional_metadata)
            
            # Prepare file data - keep file open during request
            with open(bundle_file, 'rb') as bundle_file_handle:
                # Include both files and form fields in the files parameter for proper multipart form
                files_data = {
                    "bundle": (bundle_file.name, bundle_file_handle, "application/zip"),
                }
                
                # Add form fields to files_data (httpx format for form fields in multipart)
                for key, value in form_data.items():
                    files_data[key] = (None, value)
                
                return self._request(
                    method="PUT",
                    path="/api/v1/agents/agent-definitions/{definition_id}/bundle",
                    path_params={"definition_id": definition_id},
                    files=files_data,  # Only use files parameter, no separate form_data
                    expected_status=200,
                    response_model=AgentDefinition,
                    custom_timeout=upload_timeout
                )
            
        except Exception as e:
            if isinstance(e, (MaestroError, MaestroApiError)):
                raise
            raise MaestroError(f"Failed to update bundle: {e}") from e
    
    def download_agent_definition_bundle(self, definition_id: UUID) -> bytes:
        """
        Downloads the bundle for a specific agent definition.
        
        Args:
            definition_id: UUID of the agent definition
            
        Returns:
            bytes: The bundle content as bytes
            
        Raises:
            MaestroApiError: If the agent definition does not use a bundle or the bundle is not found
        """
        return self._request(
            method="GET",
            path="/api/v1/agents/agent-definitions/{definition_id}/bundle",
            path_params={"definition_id": definition_id},
            expected_status=200,
            return_type="bytes"
        )
    
    def create_and_upload_bundle(
        self,
        source_dir: str,
        name: str,
        description: Optional[str] = None,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        interface_id: Optional[UUID] = None,
        entrypoint: str = "main.py",
        version: str = "1.0.0",
        requirements: Optional[List[str]] = None,
        additional_metadata: Optional[Dict[str, Any]] = None,
        shareable: bool = False,
        include_requirements: bool = True,
        install_dependencies: bool = True,
        maestro_config: Optional[Dict[str, Any]] = None,
        cleanup_bundle: bool = True,
        upload_timeout: float = 600.0
    ) -> AgentDefinition:
        """
        Creates a bundle from a source directory and uploads it to create an Agent Definition.
        
        This is a convenience method that combines create_bundle() and upload_agent_bundle().
        
        Args:
            source_dir: Path to the directory containing agent code
            name: Name for the Agent Definition
            description: Optional description
            input_schema: Optional input schema
            output_schema: Optional output schema
            interface_id: Optional interface ID
            entrypoint: Main entry point file for the bundle (default: "main.py")
            version: Version of the bundle (default: "1.0.0")
            requirements: Optional list of requirements (if not provided, extracted from source)
            additional_metadata: Optional additional metadata dictionary
            shareable: Whether the agent definition is shareable (default: False)
            include_requirements: Whether to automatically include requirements
            install_dependencies: Whether to install dependencies into the bundle (includes them as Python libraries)
            maestro_config: Optional maestro.yaml configuration
            cleanup_bundle: Whether to delete the temporary bundle file after upload
            upload_timeout: Timeout in seconds for the upload operation (default: 600.0)
            
        Returns:
            AgentDefinition: The created agent definition
        """
        bundle_path = None
        try:
            # Extract requirements from source if not provided and include_requirements is True
            final_requirements = requirements
            if include_requirements and not final_requirements:
                # Extract requirements from source directory
                from pathlib import Path
                source_path = Path(source_dir)
                requirements_content = self._extract_requirements(source_path)
                if requirements_content:
                    # Convert requirements.txt content to list
                    final_requirements = [req.strip() for req in requirements_content.split('\n') if req.strip()]
            
            # Create the bundle
            bundle_path = self.create_bundle(
                source_dir=source_dir,
                include_requirements=include_requirements,
                install_dependencies=install_dependencies,
                maestro_config=maestro_config
            )
            
            # Upload the bundle
            return self.upload_agent_bundle(
                bundle_path=bundle_path,
                name=name,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
                interface_id=interface_id,
                entrypoint=entrypoint,
                version=version,
                requirements=final_requirements,
                additional_metadata=additional_metadata,
                shareable=shareable,
                upload_timeout=upload_timeout
            )
            
        finally:
            # Clean up the temporary bundle file if requested
            if cleanup_bundle and bundle_path and os.path.exists(bundle_path):
                try:
                    os.remove(bundle_path)
                except Exception:
                    pass  # Ignore cleanup errors

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
    def get_bundle_download_url(self, agent_id: Optional[UUID] = None) -> str:
        """
        Get a temporary download URL for the agent's bundle.
        
        Args:
            agent_id: Optional agent ID. If not specified, uses the client's initialized agent_id.
            
        Returns:
            A temporary download URL for the agent's bundle.
            
        Raises:
            MaestroApiError: If the agent does not use a bundle or the bundle is not found.
        """
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        
        result = self._request(
            method="GET", path="/api/v1/agents/{agent_id}/bundle",
            path_params={"agent_id": agent_id_to_use},
            expected_status=200, return_type="json"
        )
        
        if not result or "download_url" not in result:
            raise MaestroError("Failed to get bundle download URL")
        
        return result["download_url"]
    
    def download_bundle(self, target_dir: Optional[str] = None, agent_id: Optional[UUID] = None) -> str:
        """
        Download the agent's bundle to a local directory.
        
        Args:
            target_dir: Directory to download the bundle to. If not specified, uses a temporary directory.
            agent_id: Optional agent ID. If not specified, uses the client's initialized agent_id.
            
        Returns:
            Path to the downloaded bundle ZIP file.
            
        Raises:
            MaestroApiError: If the agent does not use a bundle or the bundle is not found.
        """
        import tempfile
        import os
        
        agent_id_to_use = agent_id or self._ensure_agent_id_set()
        
        # Create target directory if it doesn't exist
        if not target_dir:
            target_dir = tempfile.mkdtemp(prefix="maestro_bundle_")
        elif not os.path.exists(target_dir):
            os.makedirs(target_dir)
            
        # Download the file directly from the API endpoint
        bundle_path = os.path.join(target_dir, "agent_bundle.zip")
        
        response = self._request(
            method="GET",
            path="/api/v1/agents/bundle/{agent_id}/",
            path_params={"agent_id": agent_id_to_use},
            expected_status=200,
            return_type="bytes"
        )
        
        if not response:
            raise MaestroError("Failed to download bundle")
        
        # Save the bundle
        with open(bundle_path, 'wb') as f:
            f.write(response)
            
        return bundle_path
        
    def extract_bundle(self, bundle_path: str, target_dir: Optional[str] = None) -> str:
        """
        Extract a downloaded bundle to a directory.
        
        Args:
            bundle_path: Path to the downloaded bundle ZIP file.
            target_dir: Directory to extract the bundle to. If not specified, extracts to the same directory.
            
        Returns:
            Path to the directory containing the extracted bundle.
        """
        import zipfile
        import os
        
        # Default extract location is same directory as the ZIP
        if not target_dir:
            target_dir = os.path.dirname(bundle_path)
            
        # Create extract directory if it doesn't exist
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
            
        # Extract the bundle
        with zipfile.ZipFile(bundle_path, 'r') as zip_ref:
            zip_ref.extractall(target_dir)
            
        return target_dir
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