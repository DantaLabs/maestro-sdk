from typing import List, Dict, Any, Optional
from uuid import UUID
from ..models import (
    AgentDefinitionCreate, AgentDefinition, AgentCreate, Agent, AgentUpdate, CodeExecution,
    CreateDatabaseRequest, AgentDatabase, ExecuteSQLRequest, TableInfo
)
from ..http.base import HTTPClient

class AgentResource:
    """
    Resource class for agent-related API operations.
    
    Handles all agent and agent definition operations including creation, 
    execution, service management, and database operations.
    """
    
    def __init__(self, http_client: HTTPClient, organization_id: UUID) -> None:
        """
        Initialize the AgentResource.
        
        Input:
            http_client (HTTPClient): HTTP client for making API requests.
            organization_id (UUID): Organization ID for scoping operations.
        """
        self.http = http_client
        self.organization_id = organization_id

    # Agent Definition methods
    def create_definition(self, agent_definition_data: AgentDefinitionCreate) -> AgentDefinition:
        """
        Creates an agent definition within the current organization.
        
        Input:
            agent_definition_data (AgentDefinitionCreate): Agent definition data model.
            
        Output:
            AgentDefinition: Created agent definition with ID and metadata.
        """
        payload = {"agent_definition_data": agent_definition_data.model_dump(mode='json', exclude_unset=True, exclude_none=True)}
        return self.http.request(
            method="POST", path="/api/v1/agents/agent-definitions/", json_data=payload,
            expected_status=200, response_model=AgentDefinition, organization_id=self.organization_id
        )
        
    def list_definitions(self, name: Optional[str] = None) -> List[AgentDefinition]:
        """
        Lists agent definitions within the current organization.
        
        Input:
            name (Optional[str]): Filter by agent definition name. Defaults to None.
            
        Output:
            List[AgentDefinition]: List of agent definitions matching the criteria.
        """
        query = {}
        if name:
            query["name"] = name
        return self.http.request(
            method="GET", path="/api/v1/agents/agent-definitions/",
            query_params=query if query else None,
            expected_status=200, response_model=List[AgentDefinition], organization_id=self.organization_id
        )
        
    def get_definition(self, definition_id: UUID) -> AgentDefinition:
        """
        Gets a specific agent definition by ID within the current organization.
        
        Input:
            definition_id (UUID): Unique identifier of the agent definition.
            
        Output:
            AgentDefinition: Agent definition with specified ID.
        """
        return self.http.request(
            method="GET", path="/api/v1/agents/agent-definitions/{definition_id}",
            path_params={"definition_id": definition_id},
            expected_status=200, response_model=AgentDefinition, organization_id=self.organization_id
        )
        
    def update_definition(self, definition_id: UUID, definition_data: AgentDefinitionCreate) -> AgentDefinition:
        """
        Updates an existing Agent Definition.
        
        Input:
            definition_id (UUID): Unique identifier of the agent definition to update.
            definition_data (AgentDefinitionCreate): Updated agent definition data.
            
        Output:
            AgentDefinition: Updated agent definition with new data.
        """
        payload = {"update_data": definition_data.model_dump(mode='json')}
        return self.http.request(
            method="PUT",
            path="/api/v1/agents/agent-definitions/{definition_id}",
            path_params={"definition_id": definition_id},
            json_data=payload,
            expected_status=200,
            response_model=AgentDefinition,
            organization_id=self.organization_id
        )

    # Agent instance methods
    def create(self, agent_data: AgentCreate) -> Agent:
        """Creates an agent within the current organization."""
        payload = {"agent_data": agent_data.model_dump(mode='json', exclude_unset=True, exclude_none=True)}
        return self.http.request(
            method="POST", path="/api/v1/agents/", json_data=payload,
            expected_status=200, response_model=Agent, organization_id=self.organization_id
        )
        
    def list(self, name: Optional[str] = None) -> List[Agent]:
        """Lists agents within the current organization."""
        query = {}
        if name:
            query["name"] = name
        return self.http.request(
            method="GET", path="/api/v1/agents/",
            query_params=query if query else None,
            expected_status=200, response_model=List[Agent], organization_id=self.organization_id
        )
        
    def get(self, agent_id: UUID) -> Agent:
        """Gets a specific agent by ID within the current organization."""
        return self.http.request(
            method="GET", path="/api/v1/agents/{agent_id}", path_params={"agent_id": agent_id},
            expected_status=200, response_model=Agent, organization_id=self.organization_id
        )
        
    def get_by_name(self, agent_name: str) -> Agent:
        """Gets a specific agent by name within the current organization."""
        return self.http.request(
            method="GET", path="/api/v1/agents/by-name/{agent_name}", 
            path_params={"agent_name": agent_name},
            expected_status=200, response_model=Agent, organization_id=self.organization_id
        )
        
    def update(self, agent_id: UUID, agent_data: AgentUpdate) -> Agent:
        """Updates an existing Agent."""
        payload = {"update_data": agent_data.model_dump(mode='json')}
        return self.http.request(
            method="PUT",
            path="/api/v1/agents/{agent_id}",
            path_params={"agent_id": agent_id},
            json_data=payload,
            expected_status=200,
            response_model=Agent,
            organization_id=self.organization_id
        )

    # Agent execution methods
    def execute_code(self, input_variables: Dict[str, Any], agent_id: UUID) -> CodeExecution:
        """Executes the code associated with an agent."""
        payload = {"input_variables": input_variables}
        return self.http.request(
            method="POST", path="/api/v1/agents/run/{agent_id}/execute",
            path_params={"agent_id": agent_id},
            json_data=payload,
            expected_status=200,
            organization_id=self.organization_id
        )

    def execute_code_sync(self, variables: Dict[str, Any], agent_id: UUID) -> CodeExecution:
        """Executes the code associated with an agent synchronously."""
        payload = {"input_variables": {"variables": variables}}
        return self.http.request(
            method="POST", path="/api/v1/agents/run/{agent_id}/execute-sync",
            path_params={"agent_id": agent_id},
            json_data=payload,
            expected_status=200,
            organization_id=self.organization_id
        )

    def execute_by_name(self, input_variables: Dict[str, Any], agent_name: str) -> CodeExecution:
        """Executes the code associated with an agent by name."""
        # First get the agent to find its ID
        agent = self.get_by_name(agent_name)
        return self.execute_code(input_variables, agent.id)

    def execute_by_name_sync(self, variables: Dict[str, Any], agent_name: str) -> CodeExecution:
        """Executes the code associated with an agent synchronously by name."""
        # First get the agent to find its ID
        agent = self.get_by_name(agent_name)
        return self.execute_code_sync(variables, agent.id)

    # Agent Service methods for long-running instances
    def deploy_service(self, agent_id: UUID, executor_type: Optional[str] = None, env_vars: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Deploy an agent as a Knative service for auto-scaling."""
        payload = {
            "executor_type": executor_type,
            "env_vars": env_vars
        }
        return self.http.request(
            method="POST",
            path="/api/v1/agent-services/{agent_id}/service/deploy",
            path_params={"agent_id": agent_id},
            json_data=payload,
            expected_status=200,
            organization_id=self.organization_id
        )

    def get_deployment_status(self, agent_id: UUID) -> Dict[str, Any]:
        """Get the deployment status of an agent service in Knative."""
        return self.http.request(
            method="GET",
            path="/api/v1/agent-services/{agent_id}/service/deployment/status",
            path_params={"agent_id": agent_id},
            expected_status=200,
            organization_id=self.organization_id
        )

    def start_service(self, agent_id: UUID, env_vars: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """[DEPRECATED] Start a long-running agent service. Use deploy_service() for Knative agents."""
        payload = {
            "env_vars": env_vars
        }
        return self.http.request(
            method="POST",
            path="/api/v1/agent-services/{agent_id}/service/start",
            path_params={"agent_id": agent_id},
            json_data=payload,
            expected_status=200,
            organization_id=self.organization_id
        )

    def stop_service(self, agent_id: UUID) -> None:
        """Stop a running agent service."""
        return self.http.request(
            method="DELETE",
            path="/api/v1/agent-services/{agent_id}/service/stop",
            path_params={"agent_id": agent_id},
            expected_status=204,
            organization_id=self.organization_id
        )

    def get_service_status(self, agent_id: UUID) -> Dict[str, Any]:
        """Get the status of a running agent service."""
        return self.http.request(
            method="GET",
            path="/api/v1/agent-services/{agent_id}/service/status",
            path_params={"agent_id": agent_id},
            expected_status=200,
            organization_id=self.organization_id
        )

    def list_services(self) -> List[Dict[str, Any]]:
        """List all running agent services for the organization."""
        return self.http.request(
            method="GET",
            path="/api/v1/agent-services/services/list",
            expected_status=200,
            organization_id=self.organization_id
        )

    def execute_via_service(self, agent_id: UUID, input_variables: Dict[str, Any], function_name: Optional[str] = None) -> Dict[str, Any]:
        """Execute a request via a running agent service."""
        payload = {
            "variables": input_variables,
            "function_name": function_name
        }
        return self.http.request(
            method="POST",
            path="/api/v1/agent-services/{agent_id}/service/execute",
            path_params={"agent_id": agent_id},
            json_data=payload,
            expected_status=200,
            organization_id=self.organization_id
        )

    def get_service_logs(self, agent_id: UUID, instance_id: Optional[str] = None, limit: int = 100, offset: int = 0, log_level: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get logs for a specific agent service."""
        query = {
            "limit": limit,
            "offset": offset
        }
        if instance_id:
            query["instance_id"] = instance_id
        if log_level:
            query["log_level"] = log_level

        return self.http.request(
            method="GET",
            path="/api/v1/agent-services/{agent_id}/service/logs",
            path_params={"agent_id": agent_id},
            query_params=query,
            expected_status=200,
            organization_id=self.organization_id
        )

    def get_service_metrics(self) -> Dict[str, Any]:
        """Get metrics about running agent services."""
        return self.http.request(
            method="GET",
            path="/api/v1/agent-services/services/metrics",
            expected_status=200,
            organization_id=self.organization_id
        )

    def get_service_health(self, agent_id: UUID) -> Dict[str, Any]:
        """Get health information for an agent service."""
        return self.http.request(
            method="GET",
            path="/api/v1/agent-services/{agent_id}/service/health",
            path_params={"agent_id": agent_id},
            expected_status=200,
            organization_id=self.organization_id
        )

    # Kubernetes-specific methods
    def get_kubernetes_simulation_status(self) -> Dict[str, Any]:
        """Get status of the local Kubernetes simulation (development only)."""
        return self.http.request(
            method="GET",
            path="/api/v1/agent-services/kubernetes/simulation/status",
            expected_status=200,
            organization_id=self.organization_id
        )

    def get_kubernetes_registry_images(self) -> List[Dict[str, Any]]:
        """Get cached images in the local Kubernetes registry (development only)."""
        return self.http.request(
            method="GET",
            path="/api/v1/agent-services/kubernetes/simulation/registry/images",
            expected_status=200,
            organization_id=self.organization_id
        )

    def cleanup_kubernetes_registry(self, keep_recent: int = 5) -> Dict[str, Any]:
        """Clean up old images in the local Kubernetes registry (development only)."""
        return self.http.request(
            method="POST",
            path="/api/v1/agent-services/kubernetes/simulation/registry/cleanup",
            query_params={"keep_recent": keep_recent},
            expected_status=200,
            organization_id=self.organization_id
        )

    def get_kubernetes_networks(self) -> List[Dict[str, Any]]:
        """Get Docker networks for Kubernetes simulation (development only)."""
        return self.http.request(
            method="GET",
            path="/api/v1/agent-services/kubernetes/simulation/networks",
            expected_status=200,
            organization_id=self.organization_id
        )

    # Agent Database methods
    def create_database(self, agent_id: UUID, database_request: CreateDatabaseRequest) -> AgentDatabase:
        """Create a database for an agent."""
        payload = database_request.model_dump(mode='json', exclude_unset=True, exclude_none=True)
        return self.http.request(
            method="POST",
            path="/api/v1/agents/{agent_id}/databases",
            path_params={"agent_id": agent_id},
            json_data=payload,
            expected_status=200,
            response_model=AgentDatabase,
            organization_id=self.organization_id
        )

    def list_databases(self, agent_id: UUID) -> List[AgentDatabase]:
        """List all databases for an agent."""
        return self.http.request(
            method="GET",
            path="/api/v1/agents/{agent_id}/databases",
            path_params={"agent_id": agent_id},
            expected_status=200,
            response_model=List[AgentDatabase],
            organization_id=self.organization_id
        )

    def get_database(self, agent_id: UUID, database_id: UUID) -> AgentDatabase:
        """Get a specific database for an agent."""
        # Since there's no direct GET endpoint, we list and filter
        databases = self.list_databases(agent_id)
        for db in databases:
            if db.id == database_id:
                return db
        raise ValueError(f"Database {database_id} not found for agent {agent_id}")

    def delete_database(self, agent_id: UUID, database_id: UUID) -> Dict[str, Any]:
        """Delete a database for an agent."""
        return self.http.request(
            method="DELETE",
            path="/api/v1/agents/{agent_id}/databases/{database_id}",
            path_params={"agent_id": agent_id, "database_id": database_id},
            expected_status=200,
            organization_id=self.organization_id
        )

    def execute_sql(self, agent_id: UUID, database_id: UUID, sql_request: ExecuteSQLRequest) -> Dict[str, Any]:
        """Execute SQL on an agent's database."""
        payload = sql_request.model_dump(mode='json', exclude_unset=True, exclude_none=True)
        return self.http.request(
            method="POST",
            path="/api/v1/agents/{agent_id}/databases/{database_id}/execute-sql",
            path_params={"agent_id": agent_id, "database_id": database_id},
            json_data=payload,
            expected_status=200,
            organization_id=self.organization_id
        )

    def list_database_tables(self, agent_id: UUID, database_id: UUID) -> List[TableInfo]:
        """List all tables in an agent's database."""
        return self.http.request(
            method="GET",
            path="/api/v1/agents/{agent_id}/databases/{database_id}/tables",
            path_params={"agent_id": agent_id, "database_id": database_id},
            expected_status=200,
            response_model=List[TableInfo],
            organization_id=self.organization_id
        )

    def get_table_schema(self, agent_id: UUID, database_id: UUID, table_name: str) -> Dict[str, Any]:
        """Get the schema for a specific table in an agent's database."""
        return self.http.request(
            method="GET",
            path="/api/v1/agents/{agent_id}/databases/{database_id}/tables/{table_name}/schema",
            path_params={"agent_id": agent_id, "database_id": database_id, "table_name": table_name},
            expected_status=200,
            organization_id=self.organization_id
        )

    def get_database_connection_info(self, agent_id: UUID, database_id: UUID) -> Dict[str, Any]:
        """Get transparent connection information for an agent database."""
        return self.http.request(
            method="GET",
            path="/api/v1/agents/{agent_id}/databases/{database_id}/connection-info",
            path_params={"agent_id": agent_id, "database_id": database_id},
            expected_status=200,
            organization_id=self.organization_id
        )