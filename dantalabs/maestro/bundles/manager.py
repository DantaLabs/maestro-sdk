import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from uuid import UUID
from ..models import AgentDefinition
from ..http.base import HTTPClient
from ..exceptions import MaestroError

class BundleManager:
    """Handles upload, download, and management of agent bundles."""
    
    def __init__(self, http_client: HTTPClient, organization_id: UUID):
        self.http = http_client
        self.organization_id = organization_id

    def upload_bundle(
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
        """Uploads a ZIP bundle to create a new Agent Definition."""
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
            
            # Prepare file data for the bundle
            with open(bundle_file, 'rb') as bundle_file_handle:
                files_data = {
                    "bundle": (bundle_file.name, bundle_file_handle, "application/zip"),
                }
                
                # Add form fields to files_data
                for key, value in form_data.items():
                    files_data[key] = (None, value)
                
                return self.http.request(
                    method="POST",
                    path="/api/v1/agents/agent-definitions/bundle/",
                    files=files_data,
                    expected_status=200,
                    response_model=AgentDefinition,
                    custom_timeout=upload_timeout,
                    organization_id=self.organization_id
                )
            
        except Exception as e:
            if isinstance(e, (MaestroError)):
                raise
            raise MaestroError(f"Failed to upload bundle: {e}") from e

    def update_bundle(
        self,
        definition_id: UUID,
        bundle_path: str,
        entrypoint: Optional[str] = None,
        version: Optional[str] = None,
        requirements: Optional[List[str]] = None,
        additional_metadata: Optional[Dict[str, Any]] = None,
        upload_timeout: float = 600.0
    ) -> AgentDefinition:
        """Updates an existing bundled Agent Definition with a new ZIP bundle."""
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
            
            # Prepare file data
            with open(bundle_file, 'rb') as bundle_file_handle:
                files_data = {
                    "bundle": (bundle_file.name, bundle_file_handle, "application/zip"),
                }
                
                # Add form fields to files_data
                for key, value in form_data.items():
                    files_data[key] = (None, value)
                
                return self.http.request(
                    method="PUT",
                    path="/api/v1/agents/agent-definitions/{definition_id}/bundle",
                    path_params={"definition_id": definition_id},
                    files=files_data,
                    expected_status=200,
                    response_model=AgentDefinition,
                    custom_timeout=upload_timeout,
                    organization_id=self.organization_id
                )
            
        except Exception as e:
            if isinstance(e, (MaestroError)):
                raise
            raise MaestroError(f"Failed to update bundle: {e}") from e

    def download_bundle(self, definition_id: UUID) -> bytes:
        """Downloads the bundle for a specific agent definition."""
        return self.http.request(
            method="GET",
            path="/api/v1/agents/agent-definitions/{definition_id}/bundle",
            path_params={"definition_id": definition_id},
            expected_status=200,
            return_type="bytes",
            organization_id=self.organization_id
        )

    def get_bundle_download_url(self, agent_id: UUID) -> str:
        """Get a temporary download URL for the agent's bundle."""
        result = self.http.request(
            method="GET", path="/api/v1/agent-services/bundle/{agent_id}/",
            path_params={"agent_id": agent_id},
            expected_status=200, return_type="json",
            organization_id=self.organization_id
        )
        
        if not result or "download_url" not in result:
            raise MaestroError("Failed to get bundle download URL")
        
        return result["download_url"]
    
    def download_agent_bundle(self, target_dir: Optional[str] = None, agent_id: Optional[UUID] = None) -> str:
        """Download the agent's bundle to a local directory."""
        import tempfile
        import requests
        
        if not agent_id:
            raise ValueError("agent_id is required for bundle download")
            
        # Create target directory if it doesn't exist
        if not target_dir:
            target_dir = tempfile.mkdtemp(prefix="maestro_bundle_")
        elif not os.path.exists(target_dir):
            os.makedirs(target_dir)
            
        # Get presigned URL from the API endpoint
        presigned_response = self.http.request(
            method="GET",
            path="/api/v1/agent-services/bundle/{agent_id}/get-url",
            path_params={"agent_id": agent_id},
            query_params={"agent_id": agent_id},
            expected_status=200,
            return_type="json",
            organization_id=self.organization_id
        )
        
        if not presigned_response or "presigned_url" not in presigned_response:
            raise MaestroError("Failed to get presigned URL for bundle download")
        
        presigned_url = presigned_response["presigned_url"]
        bundle_path = os.path.join(target_dir, "agent_bundle.zip")
        
        try:
            response = requests.get(presigned_url, stream=True)
            response.raise_for_status()
            
            # Save the bundle
            with open(bundle_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        except requests.RequestException as e:
            raise MaestroError(f"Failed to download bundle from presigned URL: {str(e)}")
            
        return bundle_path

    def extract_bundle(self, bundle_path: str, target_dir: Optional[str] = None) -> str:
        """Extract a downloaded bundle to a directory."""
        import zipfile
        
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

    def upload_bundle_as_image(
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
        """Uploads a ZIP bundle, builds it as a container image, and creates an Agent Definition."""
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

            # Prepare file data for the bundle
            with open(bundle_file, 'rb') as bundle_file_handle:
                files_data = {
                    "bundle": (bundle_file.name, bundle_file_handle, "application/zip"),
                }

                # Add form fields to files_data
                for key, value in form_data.items():
                    files_data[key] = (None, value)

                return self.http.request(
                    method="POST",
                    path="/api/v1/agents/agent-definitions/bundle-image/",
                    files=files_data,
                    expected_status=200,
                    response_model=AgentDefinition,
                    custom_timeout=upload_timeout,
                    organization_id=self.organization_id
                )

        except Exception as e:
            if isinstance(e, (MaestroError)):
                raise
            raise MaestroError(f"Failed to upload bundle as image: {e}") from e