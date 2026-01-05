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
    NopeFeatureError,
    NopeRateLimitError,
    NopeServerError,
    NopeValidationError,
)
from .types import (
    EvaluateConfig,
    EvaluateResponse,
    Message,
    OversightAnalyzeConfig,
    OversightAnalyzeResponse,
    OversightConversation,
    OversightIngestConfig,
    OversightIngestResponse,
    OversightMessage,
    ScreenConfig,
    ScreenResponse,
)


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
        demo: bool = False,
    ):
        """
        Initialize the NOPE client.

        Args:
            api_key: Your NOPE API key (starts with 'nope_live_' or 'nope_test_').
                     Can be None for local development/testing without auth.
            base_url: Override the API base URL. Defaults to https://api.nope.net.
            timeout: Request timeout in seconds. Defaults to 30.
            demo: Use demo/try endpoints that don't require authentication.
                  These are rate-limited but useful for testing and evaluation.
        """
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.demo = demo

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
        endpoint = "/v1/try/evaluate" if self.demo else "/v1/evaluate"
        response = self._request("POST", endpoint, json=payload)

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
        Returns independent detection flags for suicidal ideation and self-harm,
        tuned conservatively for regulatory compliance (SB243, NY Article 47).

        Either `messages` or `text` must be provided, but not both.

        Args:
            messages: List of conversation messages.
            text: Plain text input (for free-form transcripts).
            config: Configuration options (currently only debug flag).

        Returns:
            ScreenResponse with show_resources, suicidal_ideation, self_harm flags.

        Raises:
            NopeAuthError: Invalid or missing API key.
            NopeValidationError: Invalid request payload.
            NopeRateLimitError: Rate limit exceeded.
            NopeServerError: Server error.
            NopeConnectionError: Connection failed.

        Example:
            ```python
            result = client.screen(text="I've been having dark thoughts lately")

            if result.show_resources:
                print(f"SI: {result.suicidal_ideation}, SH: {result.self_harm}")
                print(f"Rationale: {result.rationale}")
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
        endpoint = "/v1/try/screen" if self.demo else "/v1/screen"
        response = self._request("POST", endpoint, json=payload)

        return ScreenResponse.model_validate(response)

    def oversight_analyze(
        self,
        *,
        conversation: Union[OversightConversation, dict],
        config: Optional[Union[OversightAnalyzeConfig, dict]] = None,
    ) -> OversightAnalyzeResponse:
        """
        Analyze a single conversation for harmful AI behaviors.

        This endpoint performs synchronous analysis and returns results directly.
        Does NOT store results to database - use `oversight_ingest` for persistent storage.

        Args:
            conversation: The conversation to analyze.
            config: Configuration options (strategy, model, etc.).

        Returns:
            OversightAnalyzeResponse with analysis result, strategy, and reason.

        Raises:
            NopeFeatureError: Oversight feature not enabled for this account.
            NopeAuthError: Invalid or missing API key.
            NopeValidationError: Invalid request payload.
            NopeServerError: Server error.
            NopeConnectionError: Connection failed.

        Example:
            ```python
            result = client.oversight_analyze(
                conversation={
                    "conversation_id": "conv_123",
                    "messages": [
                        {"role": "user", "content": "I want to end it all"},
                        {"role": "assistant", "content": "I understand how you feel..."}
                    ],
                    "metadata": {"user_is_minor": True}
                },
                config={"strategy": "sliding"}
            )

            print(f"Concern: {result.result.overall_concern}")
            print(f"Trajectory: {result.result.trajectory}")
            for behavior in result.result.detected_behaviors:
                print(f"  {behavior.code}: {behavior.severity}")
            ```
        """
        # Validate conversation
        if isinstance(conversation, dict):
            if "messages" not in conversation:
                raise ValueError('"conversation.messages" is required')
            if not isinstance(conversation["messages"], list):
                raise ValueError('"conversation.messages" must be a list')
            if len(conversation["messages"]) == 0:
                raise ValueError('"conversation.messages" cannot be empty')
        else:
            if not conversation.messages:
                raise ValueError('"conversation.messages" cannot be empty')

        # Build request payload
        payload: dict = {}

        if isinstance(conversation, dict):
            payload["conversation"] = conversation
        else:
            payload["conversation"] = conversation.model_dump(exclude_none=True)

        if config is not None:
            if isinstance(config, dict):
                payload["config"] = config
            else:
                payload["config"] = config.model_dump(exclude_none=True)

        # Make request
        endpoint = "/v1/try/oversight/analyze" if self.demo else "/v1/oversight/analyze"
        response = self._request("POST", endpoint, json=payload)

        return OversightAnalyzeResponse.model_validate(response)

    def oversight_ingest(
        self,
        *,
        conversations: List[Union[OversightConversation, dict]],
        webhook_url: Optional[str] = None,
        config: Optional[Union[OversightIngestConfig, dict]] = None,
    ) -> OversightIngestResponse:
        """
        Ingest multiple conversations for batch analysis with database storage.

        Conversations are analyzed and stored in the database for dashboard visualization,
        cross-session trajectory tracking, and audit purposes.

        Note: This endpoint is NOT available in demo mode. Requires API key with
        Oversight feature enabled.

        Args:
            conversations: List of conversations to analyze (max 100). Each must have a conversation_id.
            webhook_url: Optional URL to notify when ingestion completes.
            config: Configuration options (model).

        Returns:
            OversightIngestResponse with ingestion status and per-conversation results.

        Raises:
            NopeFeatureError: Oversight feature not enabled for this account.
            NopeAuthError: Invalid or missing API key.
            NopeValidationError: Invalid request payload.
            NopeServerError: Server error.
            NopeConnectionError: Connection failed.

        Example:
            ```python
            result = client.oversight_ingest(
                conversations=[
                    {
                        "conversation_id": "conv_001",
                        "messages": [...],
                        "metadata": {"user_id_hash": "abc123", "platform": "ios"}
                    },
                    {
                        "conversation_id": "conv_002",
                        "messages": [...],
                    }
                ],
                webhook_url="https://api.example.com/webhooks/nope"
            )

            print(f"Ingestion ID: {result.ingestion_id}")
            print(f"Processed: {result.conversations_processed}/{result.conversations_received}")
            print(f"Dashboard: {result.dashboard_url}")
            ```
        """
        if self.demo:
            raise ValueError("Oversight ingest is not available in demo mode. Use an API key.")

        # Validate conversations
        if not conversations:
            raise ValueError('"conversations" cannot be empty')
        if len(conversations) > 100:
            raise ValueError(f"Too many conversations: {len(conversations)}. Maximum allowed: 100")

        # Validate each conversation
        conv_list = []
        for i, conv in enumerate(conversations):
            if isinstance(conv, dict):
                if "conversation_id" not in conv:
                    raise ValueError(f'Conversation at index {i} must have a "conversation_id"')
                if "messages" not in conv or not conv["messages"]:
                    raise ValueError(f'Conversation "{conv["conversation_id"]}" must have non-empty "messages"')
                conv_list.append(conv)
            else:
                if not conv.conversation_id:
                    raise ValueError(f'Conversation at index {i} must have a "conversation_id"')
                if not conv.messages:
                    raise ValueError(f'Conversation "{conv.conversation_id}" must have non-empty "messages"')
                conv_list.append(conv.model_dump(exclude_none=True))

        # Build request payload
        payload: dict = {"conversations": conv_list}

        if webhook_url is not None:
            payload["webhook_url"] = webhook_url

        if config is not None:
            if isinstance(config, dict):
                payload["config"] = config
            else:
                payload["config"] = config.model_dump(exclude_none=True)

        # Make request
        response = self._request("POST", "/v1/oversight/ingest", json=payload)

        return OversightIngestResponse.model_validate(response)

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

        if response.status_code == 403:
            # Check if this is a feature access error
            try:
                import json
                error_data = json.loads(response_body)
                if error_data.get("feature"):
                    raise NopeFeatureError(
                        error_message,
                        feature=error_data.get("feature"),
                        required_access=error_data.get("required_access"),
                        response_body=response_body,
                    )
            except (json.JSONDecodeError, NopeFeatureError) as e:
                if isinstance(e, NopeFeatureError):
                    raise
                # Not a feature error, fall through to generic 403
            raise NopeError(error_message, status_code=403, response_body=response_body)

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
        demo: bool = False,
    ):
        """
        Initialize the async NOPE client.

        Args:
            api_key: Your NOPE API key. Can be None for local development/testing.
            base_url: Override the API base URL.
            timeout: Request timeout in seconds.
            demo: Use demo/try endpoints that don't require authentication.
        """
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.demo = demo

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

        endpoint = "/v1/try/evaluate" if self.demo else "/v1/evaluate"
        response = await self._request("POST", endpoint, json=payload)

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

        endpoint = "/v1/try/screen" if self.demo else "/v1/screen"
        response = await self._request("POST", endpoint, json=payload)

        return ScreenResponse.model_validate(response)

    async def oversight_analyze(
        self,
        *,
        conversation: Union[OversightConversation, dict],
        config: Optional[Union[OversightAnalyzeConfig, dict]] = None,
    ) -> OversightAnalyzeResponse:
        """
        Analyze a single conversation for harmful AI behaviors.

        See NopeClient.oversight_analyze for full documentation.
        """
        # Validate conversation
        if isinstance(conversation, dict):
            if "messages" not in conversation:
                raise ValueError('"conversation.messages" is required')
            if not isinstance(conversation["messages"], list):
                raise ValueError('"conversation.messages" must be a list')
            if len(conversation["messages"]) == 0:
                raise ValueError('"conversation.messages" cannot be empty')
        else:
            if not conversation.messages:
                raise ValueError('"conversation.messages" cannot be empty')

        # Build request payload
        payload: dict = {}

        if isinstance(conversation, dict):
            payload["conversation"] = conversation
        else:
            payload["conversation"] = conversation.model_dump(exclude_none=True)

        if config is not None:
            if isinstance(config, dict):
                payload["config"] = config
            else:
                payload["config"] = config.model_dump(exclude_none=True)

        # Make request
        endpoint = "/v1/try/oversight/analyze" if self.demo else "/v1/oversight/analyze"
        response = await self._request("POST", endpoint, json=payload)

        return OversightAnalyzeResponse.model_validate(response)

    async def oversight_ingest(
        self,
        *,
        conversations: List[Union[OversightConversation, dict]],
        webhook_url: Optional[str] = None,
        config: Optional[Union[OversightIngestConfig, dict]] = None,
    ) -> OversightIngestResponse:
        """
        Ingest multiple conversations for batch analysis with database storage.

        See NopeClient.oversight_ingest for full documentation.
        """
        if self.demo:
            raise ValueError("Oversight ingest is not available in demo mode. Use an API key.")

        # Validate conversations
        if not conversations:
            raise ValueError('"conversations" cannot be empty')
        if len(conversations) > 100:
            raise ValueError(f"Too many conversations: {len(conversations)}. Maximum allowed: 100")

        # Validate each conversation
        conv_list = []
        for i, conv in enumerate(conversations):
            if isinstance(conv, dict):
                if "conversation_id" not in conv:
                    raise ValueError(f'Conversation at index {i} must have a "conversation_id"')
                if "messages" not in conv or not conv["messages"]:
                    raise ValueError(f'Conversation "{conv["conversation_id"]}" must have non-empty "messages"')
                conv_list.append(conv)
            else:
                if not conv.conversation_id:
                    raise ValueError(f'Conversation at index {i} must have a "conversation_id"')
                if not conv.messages:
                    raise ValueError(f'Conversation "{conv.conversation_id}" must have non-empty "messages"')
                conv_list.append(conv.model_dump(exclude_none=True))

        # Build request payload
        payload: dict = {"conversations": conv_list}

        if webhook_url is not None:
            payload["webhook_url"] = webhook_url

        if config is not None:
            if isinstance(config, dict):
                payload["config"] = config
            else:
                payload["config"] = config.model_dump(exclude_none=True)

        # Make request
        response = await self._request("POST", "/v1/oversight/ingest", json=payload)

        return OversightIngestResponse.model_validate(response)

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

        if response.status_code == 403:
            # Check if this is a feature access error
            try:
                import json
                error_data = json.loads(response_body)
                if error_data.get("feature"):
                    raise NopeFeatureError(
                        error_message,
                        feature=error_data.get("feature"),
                        required_access=error_data.get("required_access"),
                        response_body=response_body,
                    )
            except (json.JSONDecodeError, NopeFeatureError) as e:
                if isinstance(e, NopeFeatureError):
                    raise
                # Not a feature error, fall through to generic 403
            raise NopeError(error_message, status_code=403, response_body=response_body)

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
