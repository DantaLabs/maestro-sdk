from typing import List, Dict, Any, Optional
from uuid import UUID
from pydantic import EmailStr
from ..models import OrganizationCreate, OrganizationRead, OrganizationUpdate, OrganizationMember
from ..http.base import HTTPClient

class OrganizationResource:
    """Resource class for organization-related API operations."""
    
    def __init__(self, http_client: HTTPClient, organization_id: Optional[UUID] = None):
        self.http = http_client
        self.organization_id = organization_id

    def create(self, org_data: OrganizationCreate) -> OrganizationRead:
        """Creates a new organization."""
        return self.http.request(
            method="POST", path="/api/v1/organizations/", json_data=org_data,
            expected_status=200, response_model=OrganizationRead, add_org_id_query=False
        )

    def verify_token_with_email(self, email: str, token: str) -> Dict[str, Any]:
        """Verifies a token with an email address to retrieve an organization ID."""
        payload = {"email": email, "token": token}
        return self.http.request(
            method="POST", path="/api/v1/organizations/verify-token", 
            json_data=payload,
            expected_status=200, response_model=None, return_type="json", add_org_id_query=False
        )

    def list_my_organizations(self) -> List[OrganizationRead]:
        """Gets a list of organizations the current user is a member of."""
        return self.http.request(
            method="GET", path="/api/v1/organizations/",
            expected_status=200, response_model=List[OrganizationRead], add_org_id_query=False
        )

    def update(self, organization_update: OrganizationUpdate) -> OrganizationRead:
        """Updates the organization specified during client initialization."""
        if not self.organization_id:
            raise ValueError("Client must be initialized with an organization_id for this operation.")
        return self.http.request(
            method="PUT", path="/api/v1/organizations/{organization_id}",
            path_params={"organization_id": self.organization_id}, json_data=organization_update,
            expected_status=200, response_model=OrganizationRead, organization_id=self.organization_id
        )

    def delete(self) -> None:
        """Deletes the organization specified during client initialization."""
        if not self.organization_id:
            raise ValueError("Client must be initialized with an organization_id for this operation.")
        return self.http.request(
            method="DELETE", path="/api/v1/organizations/{organization_id}",
            path_params={"organization_id": self.organization_id},
            expected_status=204, return_type="none", organization_id=self.organization_id
        )

    def get(self) -> OrganizationRead:
        """Reads the details of the organization specified during client initialization."""
        if not self.organization_id:
            raise ValueError("Client must be initialized with an organization_id for this operation.")
        return self.http.request(
            method="GET", path="/api/v1/organizations/{organization_id}",
            path_params={"organization_id": self.organization_id},
            expected_status=200, response_model=OrganizationRead, organization_id=self.organization_id
        )

    def get_members(self) -> List[OrganizationMember]:
        """Gets members of the organization specified during client initialization."""
        if not self.organization_id:
            raise ValueError("Client must be initialized with an organization_id for this operation.")
        return self.http.request(
            method="GET", path="/api/v1/organizations/{organization_id}/members",
            path_params={"organization_id": self.organization_id},
            expected_status=200, response_model=List[OrganizationMember], organization_id=self.organization_id
        )

    def generate_invitation_token(self, is_single_use: bool = True, expiration_days: int = 7) -> Dict[str, Any]:
        """Generates an invitation token for the current organization."""
        if not self.organization_id:
            raise ValueError("Client must be initialized with an organization_id for this operation.")
        params = {"is_single_use": is_single_use, "expiration_days": expiration_days}
        return self.http.request(
            method="POST", path="/api/v1/organizations/{organization_id}/invite",
            path_params={"organization_id": self.organization_id}, query_params=params,
            expected_status=200, response_model=None, return_type="json", organization_id=self.organization_id
        )

    def join_organization(self, token: str) -> Dict[str, Any]:
        """Allows the current user to join an organization using an invitation token."""
        params = {"token": token}
        return self.http.request(
            method="POST", path="/api/v1/organizations/join-token", query_params=params,
            expected_status=200, response_model=None, return_type="json", add_org_id_query=False
        )

    def delete_user_from_organization(self, user_id: UUID) -> Dict[str, Any]:
        """Removes a user from the organization specified during client initialization."""
        if not self.organization_id:
            raise ValueError("Client must be initialized with an organization_id for this operation.")
        return self.http.request(
            method="DELETE", path="/api/v1/organizations/{organization_id}/users/{user_id}",
            path_params={"organization_id": self.organization_id, "user_id": user_id},
            expected_status=200, response_model=None, return_type="json", organization_id=self.organization_id
        )