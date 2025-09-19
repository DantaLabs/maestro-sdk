from typing import List, Dict, Any, Optional
from uuid import UUID
from ..models import AgentDefinitionCreate, AgentDefinition, AgentCreate, Agent, AgentUpdate, CodeExecution
from ..http.base import HTTPClient

class AgentResource:
    """Resource class for agent-related API operations."""
    
    def __init__(self, http_client: HTTPClient, organization_id: UUID):
        self.http = http_client
        self.organization_id = organization_id

    # Agent Definition methods
    def create_definition(self, agent_definition_data: AgentDefinitionCreate) -> AgentDefinition:
        """Creates an agent definition within the current organization."""
        payload = {"agent_definition_data": agent_definition_data.model_dump(mode='json', exclude_unset=True, exclude_none=True)}
        return self.http.request(
            method="POST", path="/api/v1/agents/agent-definitions/", json_data=payload,
            expected_status=200, response_model=AgentDefinition, organization_id=self.organization_id
        )
        
    def list_definitions(self, name: Optional[str] = None) -> List[AgentDefinition]:
        """Lists agent definitions within the current organization."""
        query = {}
        if name:
            query["name"] = name
        return self.http.request(
            method="GET", path="/api/v1/agents/agent-definitions/",
            query_params=query if query else None,
            expected_status=200, response_model=List[AgentDefinition], organization_id=self.organization_id
        )
        
    def get_definition(self, definition_id: UUID) -> AgentDefinition:
        """Gets a specific agent definition by ID within the current organization."""
        return self.http.request(
            method="GET", path="/api/v1/agents/agent-definitions/{definition_id}",
            path_params={"definition_id": definition_id},
            expected_status=200, response_model=AgentDefinition, organization_id=self.organization_id
        )
        
    def update_definition(self, definition_id: UUID, definition_data: AgentDefinitionCreate) -> AgentDefinition:
        """Updates an existing Agent Definition."""
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
    def execute_code(self, input_variables: Dict[str, Any], agent_id: UUID, executor_type: Optional[str] = None) -> CodeExecution:
        """Executes the code associated with an agent."""
        query = {}
        if executor_type: 
            query["executor_type"] = executor_type
        payload = {"input_variables": input_variables}
        return self.http.request(
            method="POST", path="/api/v1/agents/run/{agent_id}/execute",
            path_params={"agent_id": agent_id},
            query_params=query if query else None,
            json_data=payload,
            expected_status=200,
            organization_id=self.organization_id
        )

    def execute_code_sync(self, variables: Dict[str, Any], agent_id: UUID, executor_type: Optional[str] = None) -> CodeExecution:
        """Executes the code associated with an agent synchronously."""
        query = {}
        if executor_type: 
            query["executor_type"] = executor_type
        payload = {"input_variables": {"variables": variables}}
        return self.http.request(
            method="POST", path="/api/v1/agents/run/{agent_id}/execute-sync",
            path_params={"agent_id": agent_id},
            query_params=query if query else None,
            json_data=payload,
            expected_status=200,
            organization_id=self.organization_id
        )