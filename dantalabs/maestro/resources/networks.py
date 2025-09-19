from typing import List, Dict, Any
from uuid import UUID
from ..models import NetworkGenerationRequest, NetworkResponse, NetworkListResponse
from ..http.base import HTTPClient

class NetworkResource:
    """Resource class for network-related API operations."""
    
    def __init__(self, http_client: HTTPClient, organization_id: UUID):
        self.http = http_client
        self.organization_id = organization_id

    def generate(self, request: NetworkGenerationRequest) -> NetworkResponse:
        """Generates a network based on a prompt within the current organization."""
        return self.http.request(
            method="POST", path="/api/v1/networks/generate/", json_data=request,
            expected_status=200, response_model=NetworkResponse, organization_id=self.organization_id
        )
    
    def list(self, skip: int = 0, limit: int = 100) -> NetworkListResponse:
        """Lists networks within the current organization."""
        query = {"skip": skip, "limit": limit}
        return self.http.request(
            method="GET", path="/api/v1/networks/", query_params=query,
            expected_status=200, response_model=NetworkListResponse, organization_id=self.organization_id
        )
    
    def get(self, network_id: UUID) -> NetworkResponse:
        """Gets a specific network by ID within the current organization."""
        return self.http.request(
            method="GET", path="/api/v1/networks/{network_id}", path_params={"network_id": network_id},
            expected_status=200, response_model=NetworkResponse, organization_id=self.organization_id
        )
    
    def delete(self, network_id: UUID) -> None:
        """Deletes a specific network by ID within the current organization."""
        return self.http.request(
            method="DELETE", path="/api/v1/networks/{network_id}", path_params={"network_id": network_id},
            expected_status=204, return_type="none", organization_id=self.organization_id
        )