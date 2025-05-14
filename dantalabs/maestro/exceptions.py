# maestro_sdk/exceptions.py
from typing import List, Dict, Any, Optional, Union

# --- Exceptions ---
class MaestroError(Exception):
    """Base exception class for Maestro SDK errors."""
    pass

class MaestroApiError(MaestroError):
    """Exception raised for API errors (non-2xx status codes)."""
    def __init__(self, status_code: int, error_detail: str | dict | None = None):
        self.status_code = status_code
        self.error_detail = error_detail
        message = f"API request failed with status {status_code}"
        if error_detail:
            message += f": {error_detail}"
        super().__init__(message)

class MaestroAuthError(MaestroApiError):
    """Exception raised for authentication errors (401, 403)."""
    def __init__(self, status_code: int, error_detail: str | dict | None = None):
        super().__init__(status_code, error_detail)
        self.message = f"Authentication failed with status {status_code}"
        if error_detail:
             self.message += f": {error_detail}"

class MaestroValidationError(MaestroApiError):
    """Exception raised for validation errors (422)."""
    def __init__(self, status_code: int, error_detail: dict | List | str | None = None):
        # Try to parse standard FastAPI validation errors
        self.validation_errors = []
        if isinstance(error_detail, dict) and "detail" in error_detail:
            if isinstance(error_detail["detail"], list):
                 self.validation_errors = error_detail["detail"]
            else: # Sometimes detail might just be a string
                 self.validation_errors = [{"msg": str(error_detail["detail"])}]
        elif isinstance(error_detail, list): # Sometimes FastAPI might return just the list
             self.validation_errors = error_detail
        elif isinstance(error_detail, str):
            # Handle simple string error message as a generic validation issue
            self.validation_errors = [{"msg": error_detail}]

        message = f"API request failed with validation error (status {status_code})"
        if self.validation_errors:
             # Try to format validation errors nicely
             try:
                 formatted_errors = ", ".join([f"{e.get('loc', ['unknown'])[-1] if e.get('loc') else 'field'}: {e.get('msg', 'N/A')}" for e in self.validation_errors if isinstance(e, dict)])
                 message += f": {formatted_errors}"
             except Exception:
                 message += f": {self.validation_errors}" # Fallback to raw list/dict
        elif error_detail:
             message += f": {error_detail}" # Non-standard validation error format

        super().__init__(status_code, message) # Pass formatted message up