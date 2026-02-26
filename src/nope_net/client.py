"""
NOPE SDK Client

Main client for interacting with the NOPE API.
"""

import warnings
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
    DetectCountryResponse,
    EvaluateConfig,
    EvaluateResponse,
    Message,
    OversightAnalyzeConfig,
    OversightAnalyzeResponse,
    OversightConversation,
    OversightIngestConfig,
    OversightIngestResponse,
    OversightMessage,
    ResourceByIdResponse,
    ResourcesConfig,
    ResourcesCountriesResponse,
    ResourcesResponse,
    ResourcesSmartResponse,
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

        .. deprecated::
            Use :meth:`evaluate` instead. The screen endpoint has been consolidated
            into evaluate, which now uses Edge-backed classification at $0.003/call.
            This method calls the legacy ``/v0/screen`` endpoint ($0.001/call).

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
        warnings.warn(
            "screen() is deprecated. Use evaluate() instead, which now provides "
            "Edge-backed classification at $0.003/call. screen() calls the legacy "
            "/v0/screen endpoint.",
            DeprecationWarning,
            stacklevel=2,
        )
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

        # Make request (legacy v0 endpoint)
        endpoint = "/v0/try/screen" if self.demo else "/v0/screen"
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

    # =========================================================================
    # Signpost Methods (canonical crisis resources endpoints)
    # =========================================================================

    def signpost(
        self,
        *,
        country: str,
        config: Optional[Union[ResourcesConfig, dict]] = None,
    ) -> ResourcesResponse:
        """
        Get crisis resources for a country.

        This is the basic lookup endpoint (free, no LLM). For AI-ranked results,
        use `signpost_smart()` instead.

        Args:
            country: ISO country code (e.g., "US", "GB").
            config: Optional filtering configuration (scopes, populations, limit, urgent).

        Returns:
            ResourcesResponse with crisis resources for the country.

        Raises:
            NopeAuthError: Invalid or missing API key.
            NopeValidationError: Invalid request payload.
            NopeRateLimitError: Rate limit exceeded.
            NopeServerError: Server error.
            NopeConnectionError: Connection failed.

        Example:
            ```python
            result = client.signpost(country="US")
            for resource in result.resources:
                print(f"{resource.name}: {resource.phone}")

            # With filtering
            result = client.signpost(
                country="US",
                config={"scopes": ["suicide_prevention"], "urgent": True}
            )
            ```
        """
        # Build query params
        params: dict = {"country": country.upper()}

        if config is not None:
            if isinstance(config, dict):
                cfg = config
            else:
                cfg = config.model_dump(exclude_none=True)

            if cfg.get("scopes"):
                params["scopes"] = ",".join(cfg["scopes"])
            if cfg.get("populations"):
                params["populations"] = ",".join(cfg["populations"])
            if cfg.get("limit") is not None:
                params["limit"] = str(cfg["limit"])
            if cfg.get("urgent"):
                params["urgent"] = "true"

        # Make request
        response = self._request("GET", "/v1/signpost", params=params)

        return ResourcesResponse.model_validate(response)

    def signpost_smart(
        self,
        *,
        country: str,
        query: str,
        config: Optional[Union[ResourcesConfig, dict]] = None,
    ) -> ResourcesSmartResponse:
        """
        Get AI-ranked crisis resources based on a semantic query.

        Uses LLM ranking to find the most relevant crisis resources. Costs $0.001 per call.

        Args:
            country: ISO country code (e.g., "US", "GB").
            query: Natural language query (max 500 chars).
            config: Optional filtering configuration (scopes, populations, limit).

        Returns:
            ResourcesSmartResponse with resources ranked by relevance.

        Raises:
            NopeAuthError: Invalid or missing API key.
            NopeValidationError: Invalid request payload.
            NopeRateLimitError: Rate limit exceeded.
            NopeServerError: Server error.
            NopeConnectionError: Connection failed.

        Example:
            ```python
            result = client.signpost_smart(
                country="US",
                query="teen struggling with eating disorder"
            )
            for ranked in result.ranked:
                print(f"{ranked.resource.name} (score: {ranked.score})")
                print(f"  {ranked.reasoning}")
            ```
        """
        # Build query params
        params: dict = {"country": country.upper(), "query": query}

        if config is not None:
            if isinstance(config, dict):
                cfg = config
            else:
                cfg = config.model_dump(exclude_none=True)

            if cfg.get("scopes"):
                params["scopes"] = ",".join(cfg["scopes"])
            if cfg.get("populations"):
                params["populations"] = ",".join(cfg["populations"])
            if cfg.get("limit") is not None:
                params["limit"] = str(cfg["limit"])

        # Make request - uses demo endpoint if demo mode
        endpoint = "/v1/try/signpost/smart" if self.demo else "/v1/signpost/smart"
        response = self._request("GET", endpoint, params=params)

        return ResourcesSmartResponse.model_validate(response)

    def signpost_by_id(self, resource_id: str) -> ResourceByIdResponse:
        """
        Get a single crisis resource by its database ID.

        This is a public endpoint (no auth required).

        Args:
            resource_id: UUID of the resource.

        Returns:
            ResourceByIdResponse with the crisis resource.

        Raises:
            NopeValidationError: Invalid resource ID format.
            NopeServerError: Server error.
            NopeConnectionError: Connection failed.

        Example:
            ```python
            result = client.signpost_by_id("550e8400-e29b-41d4-a716-446655440000")
            print(f"{result.resource.name}: {result.resource.phone}")
            ```
        """
        response = self._request("GET", f"/v1/signpost/{resource_id}")

        return ResourceByIdResponse.model_validate(response)

    def signpost_countries(self) -> ResourcesCountriesResponse:
        """
        List all countries with available crisis resources.

        This is a public endpoint (no auth required).

        Returns:
            ResourcesCountriesResponse with list of supported country codes.

        Raises:
            NopeServerError: Server error.
            NopeConnectionError: Connection failed.

        Example:
            ```python
            result = client.signpost_countries()
            print(f"Supported countries: {', '.join(result.countries)}")
            ```
        """
        response = self._request("GET", "/v1/signpost/countries")

        return ResourcesCountriesResponse.model_validate(response)

    def detect_country(self) -> DetectCountryResponse:
        """
        Detect user's country from request headers.

        Uses geo headers (Cloudflare, Netlify) to determine country.
        This is a public endpoint (no auth required).

        Returns:
            DetectCountryResponse with detected country code and name.

        Raises:
            NopeServerError: Server error.
            NopeConnectionError: Connection failed.

        Example:
            ```python
            result = client.detect_country()
            if result.country_code:
                print(f"Detected: {result.country_name} ({result.country_code})")
            else:
                print("Could not detect country")
            ```
        """
        response = self._request("GET", "/v1/signpost/detect-country")

        return DetectCountryResponse.model_validate(response)

    # =========================================================================
    # Deprecated Resources Methods (use signpost* methods instead)
    # =========================================================================

    def resources(
        self,
        *,
        country: str,
        config: Optional[Union[ResourcesConfig, dict]] = None,
    ) -> ResourcesResponse:
        """
        Get crisis resources for a country.

        .. deprecated::
            Use :meth:`signpost` instead. This method calls the deprecated
            ``/v1/resources`` endpoint.

        Args:
            country: ISO country code (e.g., "US", "GB").
            config: Optional filtering configuration.

        Returns:
            ResourcesResponse with crisis resources for the country.
        """
        warnings.warn(
            "resources() is deprecated and will be removed in a future version. "
            "Use signpost() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Build query params
        params: dict = {"country": country.upper()}

        if config is not None:
            if isinstance(config, dict):
                cfg = config
            else:
                cfg = config.model_dump(exclude_none=True)

            if cfg.get("scopes"):
                params["scopes"] = ",".join(cfg["scopes"])
            if cfg.get("populations"):
                params["populations"] = ",".join(cfg["populations"])
            if cfg.get("limit") is not None:
                params["limit"] = str(cfg["limit"])
            if cfg.get("urgent"):
                params["urgent"] = "true"

        response = self._request("GET", "/v1/resources", params=params)

        return ResourcesResponse.model_validate(response)

    def resources_smart(
        self,
        *,
        country: str,
        query: str,
        config: Optional[Union[ResourcesConfig, dict]] = None,
    ) -> ResourcesSmartResponse:
        """
        Get AI-ranked crisis resources based on a semantic query.

        .. deprecated::
            Use :meth:`signpost_smart` instead. This method calls the deprecated
            ``/v1/resources/smart`` endpoint.

        Args:
            country: ISO country code (e.g., "US", "GB").
            query: Natural language query (max 500 chars).
            config: Optional filtering configuration.

        Returns:
            ResourcesSmartResponse with resources ranked by relevance.
        """
        warnings.warn(
            "resources_smart() is deprecated and will be removed in a future version. "
            "Use signpost_smart() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        params: dict = {"country": country.upper(), "query": query}

        if config is not None:
            if isinstance(config, dict):
                cfg = config
            else:
                cfg = config.model_dump(exclude_none=True)

            if cfg.get("scopes"):
                params["scopes"] = ",".join(cfg["scopes"])
            if cfg.get("populations"):
                params["populations"] = ",".join(cfg["populations"])
            if cfg.get("limit") is not None:
                params["limit"] = str(cfg["limit"])

        endpoint = "/v1/try/resources/smart" if self.demo else "/v1/resources/smart"
        response = self._request("GET", endpoint, params=params)

        return ResourcesSmartResponse.model_validate(response)

    def resource_by_id(self, resource_id: str) -> ResourceByIdResponse:
        """
        Get a single crisis resource by its database ID.

        .. deprecated::
            Use :meth:`signpost_by_id` instead. This method calls the deprecated
            ``/v1/resources/:id`` endpoint.

        Args:
            resource_id: UUID of the resource.

        Returns:
            ResourceByIdResponse with the crisis resource.
        """
        warnings.warn(
            "resource_by_id() is deprecated and will be removed in a future version. "
            "Use signpost_by_id() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        response = self._request("GET", f"/v1/resources/{resource_id}")

        return ResourceByIdResponse.model_validate(response)

    def resources_countries(self) -> ResourcesCountriesResponse:
        """
        List all countries with available crisis resources.

        .. deprecated::
            Use :meth:`signpost_countries` instead. This method calls the deprecated
            ``/v1/resources/countries`` endpoint.

        Returns:
            ResourcesCountriesResponse with list of supported country codes.
        """
        warnings.warn(
            "resources_countries() is deprecated and will be removed in a future version. "
            "Use signpost_countries() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        response = self._request("GET", "/v1/resources/countries")

        return ResourcesCountriesResponse.model_validate(response)

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

        .. deprecated::
            Use :meth:`evaluate` instead. See NopeClient.screen for details.
        """
        warnings.warn(
            "screen() is deprecated. Use evaluate() instead, which now provides "
            "Edge-backed classification at $0.003/call. screen() calls the legacy "
            "/v0/screen endpoint.",
            DeprecationWarning,
            stacklevel=2,
        )
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

        # Legacy v0 endpoint
        endpoint = "/v0/try/screen" if self.demo else "/v0/screen"
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

    # =========================================================================
    # Signpost Methods (canonical crisis resources endpoints)
    # =========================================================================

    async def signpost(
        self,
        *,
        country: str,
        config: Optional[Union[ResourcesConfig, dict]] = None,
    ) -> ResourcesResponse:
        """
        Get crisis resources for a country.

        See NopeClient.signpost for full documentation.
        """
        params: dict = {"country": country.upper()}

        if config is not None:
            if isinstance(config, dict):
                cfg = config
            else:
                cfg = config.model_dump(exclude_none=True)

            if cfg.get("scopes"):
                params["scopes"] = ",".join(cfg["scopes"])
            if cfg.get("populations"):
                params["populations"] = ",".join(cfg["populations"])
            if cfg.get("limit") is not None:
                params["limit"] = str(cfg["limit"])
            if cfg.get("urgent"):
                params["urgent"] = "true"

        response = await self._request("GET", "/v1/signpost", params=params)

        return ResourcesResponse.model_validate(response)

    async def signpost_smart(
        self,
        *,
        country: str,
        query: str,
        config: Optional[Union[ResourcesConfig, dict]] = None,
    ) -> ResourcesSmartResponse:
        """
        Get AI-ranked crisis resources based on a semantic query.

        See NopeClient.signpost_smart for full documentation.
        """
        params: dict = {"country": country.upper(), "query": query}

        if config is not None:
            if isinstance(config, dict):
                cfg = config
            else:
                cfg = config.model_dump(exclude_none=True)

            if cfg.get("scopes"):
                params["scopes"] = ",".join(cfg["scopes"])
            if cfg.get("populations"):
                params["populations"] = ",".join(cfg["populations"])
            if cfg.get("limit") is not None:
                params["limit"] = str(cfg["limit"])

        endpoint = "/v1/try/signpost/smart" if self.demo else "/v1/signpost/smart"
        response = await self._request("GET", endpoint, params=params)

        return ResourcesSmartResponse.model_validate(response)

    async def signpost_by_id(self, resource_id: str) -> ResourceByIdResponse:
        """
        Get a single crisis resource by its database ID.

        See NopeClient.signpost_by_id for full documentation.
        """
        response = await self._request("GET", f"/v1/signpost/{resource_id}")

        return ResourceByIdResponse.model_validate(response)

    async def signpost_countries(self) -> ResourcesCountriesResponse:
        """
        List all countries with available crisis resources.

        See NopeClient.signpost_countries for full documentation.
        """
        response = await self._request("GET", "/v1/signpost/countries")

        return ResourcesCountriesResponse.model_validate(response)

    async def detect_country(self) -> DetectCountryResponse:
        """
        Detect user's country from request headers.

        See NopeClient.detect_country for full documentation.
        """
        response = await self._request("GET", "/v1/signpost/detect-country")

        return DetectCountryResponse.model_validate(response)

    # =========================================================================
    # Deprecated Resources Methods (use signpost* methods instead)
    # =========================================================================

    async def resources(
        self,
        *,
        country: str,
        config: Optional[Union[ResourcesConfig, dict]] = None,
    ) -> ResourcesResponse:
        """
        Get crisis resources for a country.

        .. deprecated::
            Use :meth:`signpost` instead.
        """
        warnings.warn(
            "resources() is deprecated. Use signpost() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        params: dict = {"country": country.upper()}

        if config is not None:
            if isinstance(config, dict):
                cfg = config
            else:
                cfg = config.model_dump(exclude_none=True)

            if cfg.get("scopes"):
                params["scopes"] = ",".join(cfg["scopes"])
            if cfg.get("populations"):
                params["populations"] = ",".join(cfg["populations"])
            if cfg.get("limit") is not None:
                params["limit"] = str(cfg["limit"])
            if cfg.get("urgent"):
                params["urgent"] = "true"

        response = await self._request("GET", "/v1/resources", params=params)

        return ResourcesResponse.model_validate(response)

    async def resources_smart(
        self,
        *,
        country: str,
        query: str,
        config: Optional[Union[ResourcesConfig, dict]] = None,
    ) -> ResourcesSmartResponse:
        """
        Get AI-ranked crisis resources based on a semantic query.

        .. deprecated::
            Use :meth:`signpost_smart` instead.
        """
        warnings.warn(
            "resources_smart() is deprecated. Use signpost_smart() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        params: dict = {"country": country.upper(), "query": query}

        if config is not None:
            if isinstance(config, dict):
                cfg = config
            else:
                cfg = config.model_dump(exclude_none=True)

            if cfg.get("scopes"):
                params["scopes"] = ",".join(cfg["scopes"])
            if cfg.get("populations"):
                params["populations"] = ",".join(cfg["populations"])
            if cfg.get("limit") is not None:
                params["limit"] = str(cfg["limit"])

        endpoint = "/v1/try/resources/smart" if self.demo else "/v1/resources/smart"
        response = await self._request("GET", endpoint, params=params)

        return ResourcesSmartResponse.model_validate(response)

    async def resource_by_id(self, resource_id: str) -> ResourceByIdResponse:
        """
        Get a single crisis resource by its database ID.

        .. deprecated::
            Use :meth:`signpost_by_id` instead.
        """
        warnings.warn(
            "resource_by_id() is deprecated. Use signpost_by_id() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        response = await self._request("GET", f"/v1/resources/{resource_id}")

        return ResourceByIdResponse.model_validate(response)

    async def resources_countries(self) -> ResourcesCountriesResponse:
        """
        List all countries with available crisis resources.

        .. deprecated::
            Use :meth:`signpost_countries` instead.
        """
        warnings.warn(
            "resources_countries() is deprecated. Use signpost_countries() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        response = await self._request("GET", "/v1/resources/countries")

        return ResourcesCountriesResponse.model_validate(response)

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
