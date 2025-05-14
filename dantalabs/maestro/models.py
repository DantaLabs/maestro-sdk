# maestro_sdk/models.py
import io
import os
import collections.abc
import copy
from typing import Optional, Dict, Any, List, Union, Tuple, Iterator
from uuid import UUID, uuid4
from pydantic import BaseModel, Field, EmailStr, UUID4, model_validator
from datetime import datetime
# from typing import get_origin, get_args # For more robust list model validation if needed

# --- Base Models ---
class MaestroBaseModel(BaseModel):
    class Config:
        extra = 'allow'

# --- Schemas from components/schemas ---
class Token(MaestroBaseModel):
    access_token: str
    token_type: str = "bearer"


class Message(MaestroBaseModel):
    message: str


class ValidationError(MaestroBaseModel):
    loc: List[Union[str, int]]
    msg: str
    type: str

class HTTPValidationError(MaestroBaseModel):
    detail: Optional[List[ValidationError]] = None

class OrganizationCreate(MaestroBaseModel):
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    phone_number: Optional[str] = None
    email: EmailStr
    is_personal: bool = False

class OrganizationRead(MaestroBaseModel):
    id: UUID4
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    phone_number: Optional[str] = None
    email: EmailStr
    is_personal: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

class OrganizationUpdate(MaestroBaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None

class OrganizationMember(MaestroBaseModel):
    id: Optional[UUID4] = None
    full_name: Optional[str] = None
    email: EmailStr

class AgentDefinitionCreate(MaestroBaseModel):
    name: str
    description: Optional[str] = None
    definition: str
    definition_type: Optional[str] = 'python'
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    interface_id: Optional[UUID4] = None
    memory_template: Dict[str, Any] = Field(default_factory=dict)
    environment_variables: Optional[Dict[str, Any]] = Field(default_factory=dict)

class AgentDefinition(MaestroBaseModel):
    id: UUID4
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    definition: str = ""
    definition_type: Optional[str] = 'python'
    memory_template: Dict[str, Any]
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    access_level: str = 'organization'
    created_at: datetime
    updated_at: datetime
    organization_id: Optional[UUID4] = None # API response might still include it
    interface_id: Optional[UUID4] = None
    environment_variables: Optional[Dict[str, Any]] = Field(default_factory=dict)

class AgentCreate(MaestroBaseModel):
    name: str
    description: Optional[str] = None
    agent_type: str
    capabilities: Optional[List[str]] = Field(default_factory=list)
    agent_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    agent_definition_id: UUID4
    memory_config: Optional[Dict[str, Any]] = None
    secrets: Optional[Dict[str, Any]] = Field(default_factory=dict)

class AgentUpdate(MaestroBaseModel):
    """
    Model for updating an Agent.
    """
    name: Optional[str] = None
    description: Optional[str] = None
    agent_type: Optional[str] = None
    capabilities: Optional[List[str]] = Field(default_factory=list)
    agent_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    agent_definition_id: Optional[UUID4] = None
    #memory_config: Optional[Dict[str, Any]] = None
    secrets: Optional[Dict[str, Any]] = Field(default_factory=dict)

class Agent(MaestroBaseModel):
    id: UUID4
    name: str = Field(..., max_length=50)
    description: Optional[str] = None
    capabilities: Optional[List[str]] = None
    agent_metadata: Optional[Dict[str, Any]] = None
    agent_type: str = Field(..., max_length=20)
    created_at: datetime
    updated_at: datetime
    agent_definition_id: Optional[UUID4] = None
    organization_id: Optional[UUID4] = None # API response might still include it

class NetworkGenerationRequest(MaestroBaseModel):
    prompt: str

class NetworkNodeResponse(MaestroBaseModel):
    id: UUID4
    agent_id: UUID4
    node_metadata: Optional[Dict[str, Any]] = None

class MemoryUpdate(MaestroBaseModel):
    """Client-side model for updating Memory, matching server-side MemoryUpdate"""
    name: Optional[str] = None
    description: Optional[str] = None
    memory_metadata: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    update_strategy: str = "merge"  # Options: "merge" (default) or "replace"

class NetworkConnectionResponse(MaestroBaseModel):
    id: UUID4
    source_node_id: UUID4
    target_node_id: UUID4
    adapter_id: UUID4
    connection_metadata: Optional[Dict[str, Any]] = None

class NetworkResponse(MaestroBaseModel):
    id: UUID4
    name: str
    description: Optional[str] = None
    organization_id: UUID4 # API response will include it
    created_at: datetime
    updated_at: datetime
    network_metadata: Optional[Dict[str, Any]] = None
    nodes: List[NetworkNodeResponse] = Field(default_factory=list)
    connections: List[NetworkConnectionResponse] = Field(default_factory=list)

class NetworkListResponse(MaestroBaseModel):
    networks: List[NetworkResponse] = Field(default_factory=list)
    count: int

class NetworkErrorResponse(MaestroBaseModel):
    error: str

class AdapterCreate(MaestroBaseModel):
    name: str
    description: Optional[str] = None
    adapter_type: str = 'agent-agent'
    adapter_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    code: Optional[str] = None

class AdapterUpdate(MaestroBaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    adapter_type: Optional[str] = None
    adapter_metadata: Optional[Dict[str, Any]] = None
    code: Optional[str] = None

class AdapterResponse(MaestroBaseModel):
    id: UUID4
    name: str
    description: Optional[str] = None
    adapter_type: str
    adapter_metadata: Dict[str, Any]
    organization_id: Optional[UUID4] = None # API response might still include it
    code: Optional[str] = None

class AdapterListResponse(MaestroBaseModel):
    adapters: List[AdapterResponse]
    count: int

class CodeExecution(MaestroBaseModel):
    id: Optional[UUID4] = None
    interaction_id: Optional[UUID4] = None
   
    execution_result: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    executed_at: Optional[datetime] = None
    duration: Optional[float] = None

class ReturnFile(MaestroBaseModel):
    id: UUID4
    file_name: str
    file_type: str
    created_at: datetime