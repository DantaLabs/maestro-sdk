import httpx
from typing import Optional, Dict, Any, List, Union, Tuple
from uuid import UUID
from ..models import MaestroBaseModel
from ..exceptions import (
    MaestroError,
    MaestroApiError,
    MaestroAuthError,
    MaestroValidationError,
)


def _clean_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Removes keys with None values from parameters dictionary.

    Input:
        params (Dict[str, Any]): Dictionary containing parameters with possible None values.

    Output:
        Dict[str, Any]: Cleaned dictionary with None values removed.
    """
    return {k: v for k, v in params.items() if v is not None}


class HTTPClient:
    """
    HTTP client for making requests to the Maestro API.

    Handles authentication, request formatting, and error handling for all API calls.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout: float = 120.0,
        raise_for_status: bool = True,
    ) -> None:
        """
        Initialize the HTTP client.

        Input:
            base_url (str): Base URL for the Maestro API.
            token (str): Authentication token for API requests.
            timeout (float): Request timeout in seconds. Defaults to 120.0.
            raise_for_status (bool): Whether to raise exceptions for non-2xx responses. Defaults to True.
        """
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._raise_for_status = raise_for_status
        self._client: Optional[httpx.Client] = None

    def _get_client(self) -> httpx.Client:
        """
        Initializes or returns the httpx client.

        Output:
            httpx.Client: Configured HTTP client instance.
        """
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(
                base_url=self.base_url, timeout=self._timeout, follow_redirects=True
            )
        return self._client

    def _get_client_with_timeout(self, timeout: float) -> httpx.Client:
        """
        Returns a httpx client with a custom timeout for specific operations.

        Input:
            timeout (float): Custom timeout in seconds.

        Output:
            httpx.Client: HTTP client with custom timeout.
        """
        return httpx.Client(
            base_url=self.base_url, timeout=timeout, follow_redirects=True
        )

    def _update_headers(
        self, headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """
        Adds Authorization header if token exists.

        Input:
            headers (Optional[Dict[str, str]]): Additional headers to include.

        Output:
            Dict[str, str]: Headers with authorization and content-type added.

        Raises:
            MaestroAuthError: If authentication token is not set.
        """
        final_headers = headers or {}
        final_headers.setdefault("Accept", "application/json")
        if not self._token:
            raise MaestroAuthError(401, "Authentication token is not set.")
        final_headers["Authorization"] = f"Bearer {self._token}"
        return final_headers

    def request(
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
        custom_timeout: Optional[float] = None,
        organization_id: Optional[UUID] = None,
    ) -> Any:
        """
        Internal helper for making requests to the Maestro API.

        Automatically adds organization_id query param unless add_org_id_query=False.
        Handles authentication, serialization, and error handling for all API calls.

        Input:
            method (str): HTTP method (GET, POST, PUT, DELETE, etc.).
            path (str): API endpoint path with optional placeholders.
            path_params (Optional[Dict[str, Any]]): Parameters to substitute in path placeholders.
            query_params (Optional[Dict[str, Any]]): Query parameters for the request.
            json_data (Optional[Any]): JSON data to send in request body.
            form_data (Optional[Dict[str, str]]): Form data to send in request body.
            files (Optional[Dict[str, Tuple[str, Any, str]]]): Files to upload.
            expected_status (int): Expected HTTP status code. Defaults to 200.
            response_model (Optional[type[MaestroBaseModel]]): Pydantic model for response parsing.
            return_type (str): Type of response to return ("json", "text", "none"). Defaults to "json".
            add_org_id_query (bool): Whether to add organization_id to query params. Defaults to True.
            custom_timeout (Optional[float]): Custom timeout for this request.
            organization_id (Optional[UUID]): Organization ID to add to query params.

        Output:
            Any: Parsed response data based on return_type and response_model.

        Raises:
            MaestroApiError: For non-2xx HTTP status codes.
            MaestroAuthError: For authentication-related errors.
            MaestroValidationError: For validation errors (422).
            ValueError: For parameter formatting errors.
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
                raise ValueError(
                    f"Error formatting path '{path}' with params {path_params}: {e}"
                ) from e

        headers = (
            self._update_headers()
        )  # This will raise MaestroAuthError if token is needed but missing
        content_to_send = None
        files_to_send = None

        request_query_params = query_params or {}

        if add_org_id_query and organization_id:
            request_query_params.setdefault("organization_id", str(organization_id))

        str_query_params = {}
        for k, v in request_query_params.items():
            if isinstance(v, bool):
                str_query_params[k] = str(v).lower()
            elif isinstance(v, UUID):
                str_query_params[k] = str(v)
            elif v is not None:
                str_query_params[k] = str(v)

        final_query_params = _clean_params(str_query_params)

        # Handle request body
        current_json_data = json_data
        if current_json_data is not None:
            if isinstance(current_json_data, MaestroBaseModel):
                content_to_send = current_json_data.model_dump(
                    mode="json", exclude_unset=True, exclude_none=True
                )
            else:

                def stringify_uuids(d):
                    if isinstance(d, dict):
                        return {k: stringify_uuids(v) for k, v in d.items()}
                    if isinstance(d, list):
                        return [stringify_uuids(i) for i in d]
                    if isinstance(d, UUID):
                        return str(d)
                    return d

                content_to_send = stringify_uuids(current_json_data)
            if not files and not form_data:
                headers["Content-Type"] = "application/json"
        elif form_data:
            content_to_send = form_data
        elif files:
            files_to_send = files
            content_to_send = None

        try:
            response = http_client.request(
                method,
                url_path,
                params=final_query_params if files or (not form_data) else None,
                json=(
                    content_to_send
                    if current_json_data is not None and not (form_data or files)
                    else None
                ),
                data=content_to_send if form_data and not files else None,
                files=files_to_send,
                headers=headers,
            )

            if self._raise_for_status and not (200 <= response.status_code < 300):
                error_detail: Any = None
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = (
                        response.text or f"Status Code {response.status_code}, No Body"
                    )

                if response.status_code in (401, 403):
                    raise MaestroAuthError(response.status_code, error_detail)
                elif response.status_code == 422:
                    raise MaestroValidationError(response.status_code, error_detail)
                else:
                    raise MaestroApiError(response.status_code, error_detail)

            elif (
                not (200 <= response.status_code < 300)
                and response.status_code != expected_status
            ):
                print(
                    f"Warning: Received status code {response.status_code}, expected {expected_status}. raise_for_status is False."
                )

            elif response.status_code == 204:
                if expected_status != 204:
                    print(
                        f"Warning: Received 204 No Content, but expected status {expected_status}."
                    )
                return None

            if return_type == "none":
                return None
            if return_type == "json":
                try:
                    resp_json = response.json()
                except Exception as e:
                    raise MaestroError(
                        f"Failed to decode JSON response (Status: {response.status_code}): {e}\nResponse Text: {response.text[:500]}..."
                    ) from e

                if response_model:
                    try:
                        is_list_model = getattr(response_model, "__origin__", None) in (
                            list,
                            List,
                        )

                        if isinstance(resp_json, list) and is_list_model:
                            item_model = response_model.__args__[0]
                            return [
                                item_model.model_validate(item) for item in resp_json
                            ]
                        elif not isinstance(resp_json, list) and not is_list_model:
                            return response_model.model_validate(resp_json)
                        elif isinstance(resp_json, dict) and is_list_model:
                            return response_model.model_validate(resp_json)
                        else:
                            raise MaestroError(
                                f"Response JSON type ({type(resp_json).__name__}) does not match expected model type ({response_model}). JSON: {str(resp_json)[:200]}..."
                            )
                    except Exception as e:
                        raise MaestroError(
                            f"Failed to parse response into {response_model}: {e}\nResponse JSON: {str(resp_json)[:500]}..."
                        ) from e
                else:
                    return resp_json
            elif return_type == "text":
                return response.text
            elif return_type == "bytes":
                return response.content
            elif return_type == "response":
                return response
            else:
                raise ValueError(f"Invalid return_type specified: {return_type}")

        except httpx.RequestError as e:
            raise MaestroError(f"HTTP request failed: {e}") from e
        except MaestroError:
            raise
        except Exception as e:
            raise MaestroError(
                f"An unexpected error occurred during the request processing: {e}"
            ) from e
        finally:
            if use_custom_client and http_client and not http_client.is_closed:
                http_client.close()

    def close(self) -> None:
        """
        Closes the underlying HTTP client connection.

        Properly closes the httpx client to free resources and prevent connection leaks.
        """
        if hasattr(self, "_client") and self._client and not self._client.is_closed:
            self._client.close()
