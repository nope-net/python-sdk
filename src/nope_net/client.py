"""
NOPE SDK Client

Main client for interacting with the NOPE API.
"""

from typing import List, Optional, Union

import httpx

from .errors import (
    NopeAuthError,
    NopeConnectionError,
    NopeError,
    NopeRateLimitError,
    NopeServerError,
    NopeValidationError,
)
from .types import EvaluateConfig, EvaluateResponse, Message, ScreenConfig, ScreenResponse


class NopeClient:
    """
    Client for the NOPE safety API.

    Example:
        ```python
        from nope import NopeClient

        client = NopeClient(api_key="nope_live_...")
        result = client.evaluate(
            messages=[{"role": "user", "content": "I'm feeling down"}],
            config={"user_country": "US"}
        )
        print(result.summary.speaker_severity)
        ```
    """

    DEFAULT_BASE_URL = "https://api.nope.net"
    DEFAULT_TIMEOUT = 30.0  # seconds

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """
        Initialize the NOPE client.

        Args:
            api_key: Your NOPE API key (starts with 'nope_live_' or 'nope_test_').
                     Can be None for local development/testing without auth.
            base_url: Override the API base URL. Defaults to https://api.nope.net.
            timeout: Request timeout in seconds. Defaults to 30.
        """
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout or self.DEFAULT_TIMEOUT

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "nope-python/0.1.0",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=headers,
        )

    def __enter__(self) -> "NopeClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def evaluate(
        self,
        *,
        messages: Optional[List[Union[Message, dict]]] = None,
        text: Optional[str] = None,
        config: Optional[Union[EvaluateConfig, dict]] = None,
        user_context: Optional[str] = None,
        proposed_response: Optional[str] = None,
    ) -> EvaluateResponse:
        """
        Evaluate conversation messages for safety risks.

        Either `messages` or `text` must be provided, but not both.

        Args:
            messages: List of conversation messages. Each message should have
                'role' ('user' or 'assistant') and 'content'.
            text: Plain text input (for free-form transcripts or session notes).
            config: Configuration options including user_country, locale, etc.
            user_context: Free-text context about the user to help shape responses.
            proposed_response: Optional proposed AI response to evaluate for appropriateness.

        Returns:
            EvaluateResponse with risks, summary, communication, crisis resources, etc.

        Raises:
            NopeAuthError: Invalid or missing API key.
            NopeValidationError: Invalid request payload.
            NopeRateLimitError: Rate limit exceeded.
            NopeServerError: Server error.
            NopeConnectionError: Connection failed.

        Example:
            ```python
            result = client.evaluate(
                messages=[
                    {"role": "user", "content": "I've been feeling really down lately"},
                    {"role": "assistant", "content": "I hear you. Can you tell me more?"},
                    {"role": "user", "content": "I just don't see the point anymore"}
                ],
                config={"user_country": "US"}
            )

            if result.summary.speaker_severity in ("high", "critical"):
                print("High risk detected")
                for resource in result.crisis_resources:
                    print(f"  {resource.name}: {resource.phone}")
            ```
        """
        if messages is None and text is None:
            raise ValueError("Either 'messages' or 'text' must be provided")
        if messages is not None and text is not None:
            raise ValueError("Only one of 'messages' or 'text' can be provided, not both")

        # Build request payload
        payload: dict = {}

        if messages is not None:
            payload["messages"] = [
                m if isinstance(m, dict) else m.model_dump(exclude_none=True) for m in messages
            ]

        if text is not None:
            payload["text"] = text

        if config is not None:
            if isinstance(config, dict):
                payload["config"] = config
            else:
                payload["config"] = config.model_dump(exclude_none=True)
        else:
            payload["config"] = {}

        if user_context is not None:
            payload["user_context"] = user_context

        if proposed_response is not None:
            payload["proposed_response"] = proposed_response

        # Make request
        response = self._request("POST", "/v1/evaluate", json=payload)

        return EvaluateResponse.model_validate(response)

    def screen(
        self,
        *,
        messages: Optional[List[Union[Message, dict]]] = None,
        text: Optional[str] = None,
        config: Optional[Union[ScreenConfig, dict]] = None,
    ) -> ScreenResponse:
        """
        Lightweight crisis screening for SB243/regulatory compliance.

        Fast, cheap endpoint for detecting suicidal ideation and self-harm.
        Uses C-SSRS framework for evidence-based severity assessment.

        Either `messages` or `text` must be provided, but not both.

        Args:
            messages: List of conversation messages.
            text: Plain text input (for free-form transcripts).
            config: Configuration options (currently only debug flag).

        Returns:
            ScreenResponse with referral_required, cssrs_level, crisis_type, etc.

        Raises:
            NopeAuthError: Invalid or missing API key.
            NopeValidationError: Invalid request payload.
            NopeRateLimitError: Rate limit exceeded.
            NopeServerError: Server error.
            NopeConnectionError: Connection failed.

        Example:
            ```python
            result = client.screen(text="I've been having dark thoughts lately")

            if result.referral_required:
                print(f"Crisis detected: {result.crisis_type}")
                print(f"C-SSRS level: {result.cssrs_level}")
                if result.resources:
                    print(f"Call {result.resources.primary.phone}")
            ```
        """
        if messages is None and text is None:
            raise ValueError("Either 'messages' or 'text' must be provided")
        if messages is not None and text is not None:
            raise ValueError("Only one of 'messages' or 'text' can be provided, not both")

        # Build request payload
        payload: dict = {}

        if messages is not None:
            payload["messages"] = [
                m if isinstance(m, dict) else m.model_dump(exclude_none=True) for m in messages
            ]

        if text is not None:
            payload["text"] = text

        if config is not None:
            if isinstance(config, dict):
                payload["config"] = config
            else:
                payload["config"] = config.model_dump(exclude_none=True)

        # Make request
        response = self._request("POST", "/v1/screen", json=payload)

        return ScreenResponse.model_validate(response)

    def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:
        """
        Make an HTTP request to the API.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., '/v1/evaluate')
            **kwargs: Additional arguments passed to httpx.request()

        Returns:
            Parsed JSON response.

        Raises:
            NopeAuthError: 401 response.
            NopeValidationError: 400 response.
            NopeRateLimitError: 429 response.
            NopeServerError: 5xx response.
            NopeConnectionError: Connection failed.
        """
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.ConnectError as e:
            raise NopeConnectionError(
                f"Failed to connect to {self.base_url}",
                original_error=e,
            ) from e
        except httpx.TimeoutException as e:
            raise NopeConnectionError(
                f"Request timed out after {self.timeout}s",
                original_error=e,
            ) from e
        except httpx.HTTPError as e:
            raise NopeConnectionError(
                f"HTTP error: {e}",
                original_error=e,
            ) from e

        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> dict:
        """
        Handle API response, raising appropriate errors for non-2xx status codes.
        """
        if response.is_success:
            return response.json()

        # Try to parse error message from response
        try:
            error_data = response.json()
            error_message = error_data.get("error", response.text)
        except Exception:
            error_message = response.text

        response_body = response.text

        if response.status_code == 401:
            raise NopeAuthError(error_message, response_body=response_body)

        if response.status_code == 400:
            raise NopeValidationError(error_message, response_body=response_body)

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_after_seconds = float(retry_after) if retry_after else None
            raise NopeRateLimitError(
                error_message,
                retry_after=retry_after_seconds,
                response_body=response_body,
            )

        if response.status_code >= 500:
            raise NopeServerError(
                error_message,
                status_code=response.status_code,
                response_body=response_body,
            )

        # Generic error for other status codes
        raise NopeError(
            error_message,
            status_code=response.status_code,
            response_body=response_body,
        )


class AsyncNopeClient:
    """
    Async client for the NOPE safety API.

    Example:
        ```python
        from nope import AsyncNopeClient

        async with AsyncNopeClient(api_key="nope_live_...") as client:
            result = await client.evaluate(
                messages=[{"role": "user", "content": "I'm feeling down"}],
                config={"user_country": "US"}
            )
            print(result.summary.speaker_severity)
        ```
    """

    DEFAULT_BASE_URL = "https://api.nope.net"
    DEFAULT_TIMEOUT = 30.0  # seconds

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """
        Initialize the async NOPE client.

        Args:
            api_key: Your NOPE API key. Can be None for local development/testing.
            base_url: Override the API base URL.
            timeout: Request timeout in seconds.
        """
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout or self.DEFAULT_TIMEOUT

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "nope-python/0.1.0",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=headers,
        )

    async def __aenter__(self) -> "AsyncNopeClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def evaluate(
        self,
        *,
        messages: Optional[List[Union[Message, dict]]] = None,
        text: Optional[str] = None,
        config: Optional[Union[EvaluateConfig, dict]] = None,
        user_context: Optional[str] = None,
        proposed_response: Optional[str] = None,
    ) -> EvaluateResponse:
        """
        Evaluate conversation messages for safety risks.

        See NopeClient.evaluate for full documentation.
        """
        if messages is None and text is None:
            raise ValueError("Either 'messages' or 'text' must be provided")
        if messages is not None and text is not None:
            raise ValueError("Only one of 'messages' or 'text' can be provided, not both")

        payload: dict = {}

        if messages is not None:
            payload["messages"] = [
                m if isinstance(m, dict) else m.model_dump(exclude_none=True) for m in messages
            ]

        if text is not None:
            payload["text"] = text

        if config is not None:
            if isinstance(config, dict):
                payload["config"] = config
            else:
                payload["config"] = config.model_dump(exclude_none=True)
        else:
            payload["config"] = {}

        if user_context is not None:
            payload["user_context"] = user_context

        if proposed_response is not None:
            payload["proposed_response"] = proposed_response

        response = await self._request("POST", "/v1/evaluate", json=payload)

        return EvaluateResponse.model_validate(response)

    async def screen(
        self,
        *,
        messages: Optional[List[Union[Message, dict]]] = None,
        text: Optional[str] = None,
        config: Optional[Union[ScreenConfig, dict]] = None,
    ) -> ScreenResponse:
        """
        Lightweight crisis screening for SB243/regulatory compliance.

        See NopeClient.screen for full documentation.
        """
        if messages is None and text is None:
            raise ValueError("Either 'messages' or 'text' must be provided")
        if messages is not None and text is not None:
            raise ValueError("Only one of 'messages' or 'text' can be provided, not both")

        payload: dict = {}

        if messages is not None:
            payload["messages"] = [
                m if isinstance(m, dict) else m.model_dump(exclude_none=True) for m in messages
            ]

        if text is not None:
            payload["text"] = text

        if config is not None:
            if isinstance(config, dict):
                payload["config"] = config
            else:
                payload["config"] = config.model_dump(exclude_none=True)

        response = await self._request("POST", "/v1/screen", json=payload)

        return ScreenResponse.model_validate(response)

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs,
    ) -> dict:
        """Make an async HTTP request to the API."""
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.ConnectError as e:
            raise NopeConnectionError(
                f"Failed to connect to {self.base_url}",
                original_error=e,
            ) from e
        except httpx.TimeoutException as e:
            raise NopeConnectionError(
                f"Request timed out after {self.timeout}s",
                original_error=e,
            ) from e
        except httpx.HTTPError as e:
            raise NopeConnectionError(
                f"HTTP error: {e}",
                original_error=e,
            ) from e

        return self._handle_response(response)

    def _handle_response(self, response: httpx.Response) -> dict:
        """Handle API response."""
        if response.is_success:
            return response.json()

        try:
            error_data = response.json()
            error_message = error_data.get("error", response.text)
        except Exception:
            error_message = response.text

        response_body = response.text

        if response.status_code == 401:
            raise NopeAuthError(error_message, response_body=response_body)

        if response.status_code == 400:
            raise NopeValidationError(error_message, response_body=response_body)

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_after_seconds = float(retry_after) if retry_after else None
            raise NopeRateLimitError(
                error_message,
                retry_after=retry_after_seconds,
                response_body=response_body,
            )

        if response.status_code >= 500:
            raise NopeServerError(
                error_message,
                status_code=response.status_code,
                response_body=response_body,
            )

        raise NopeError(
            error_message,
            status_code=response.status_code,
            response_body=response_body,
        )
