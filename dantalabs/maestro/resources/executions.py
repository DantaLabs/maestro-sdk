from typing import List
from uuid import UUID
from ..models import CodeExecution
from ..http.base import HTTPClient

class ExecutionResource:
    """Resource class for execution-related API operations."""
    
    def __init__(self, http_client: HTTPClient, organization_id: UUID):
        self.http = http_client
        self.organization_id = organization_id

    def get_status(self, execution_id: UUID) -> CodeExecution:
        """Gets the status of a specific code execution within the organization."""
        return self.http.request(
            method="GET", path="/api/v1/agents/executions/{execution_id}",
            path_params={"execution_id": execution_id},
            expected_status=200, organization_id=self.organization_id
        )
        
    def list(self, limit: int = 10, skip: int = 0) -> List[CodeExecution]:
        """Lists code executions within the current organization."""
        query = {"limit": limit, "skip": skip}
        return self.http.request(
            method="GET", path="/api/v1/agents/executions", query_params=query,
            expected_status=200, response_model=List[CodeExecution], organization_id=self.organization_id
        )