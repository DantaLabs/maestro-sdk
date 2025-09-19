import io
from typing import Optional, Union
from uuid import UUID
from pydantic import EmailStr
from ..models import ReturnFile, Message
from ..http.base import HTTPClient, _clean_params

class FileResource:
    """Resource class for file-related API operations."""
    
    def __init__(self, http_client: HTTPClient, organization_id: UUID):
        self.http = http_client
        self.organization_id = organization_id

    def upload(self, file: io.BytesIO, filename: str, content_type: str,
               project_id: Optional[Union[UUID, str]] = None, 
               task_id: Optional[Union[UUID, str]] = None,
               chat_id: Optional[Union[UUID, str]] = None) -> ReturnFile:
        """Upload a file associated with the client's organization."""
        form_data_fields = {
            "project_id": str(project_id) if project_id else None,
            "task_id": str(task_id) if task_id else None,
            "chat_id": str(chat_id) if chat_id else None,
        }
        files_data = {"uploaded_file": (filename, file, content_type)}

        return self.http.request(
            method="POST", path="/api/v1/files/upload/",
            form_data=_clean_params(form_data_fields),
            files=files_data,
            expected_status=200, response_model=ReturnFile,
            organization_id=self.organization_id
        )

class UtilityResource:
    """Resource class for utility operations."""
    
    def __init__(self, http_client: HTTPClient):
        self.http = http_client

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

    def test_email(self, email_to: EmailStr) -> Message:
        """Sends a test email via the Maestro service."""
        params = {"email_to": email_to}
        return self.http.request(
            method="POST", path="/api/v1/utils/test-email/", query_params=params,
            expected_status=201, response_model=Message, add_org_id_query=False
        )