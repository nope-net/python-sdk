"""
NOPE SDK Client

Main client for interacting with the NOPE API.
"""

import asyncio
import time
import warnings
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, Union

import httpx

from ._http import (
    DEFAULT_MAX_RETRIES,
    ResponseMeta,
    build_error,
    connection_error_from,
    decode_success,
    is_retryable,
    parse_response_meta,
    retry_wait_seconds,
)
from ._requests import build_evaluate_request, build_screen_request
from .types import (
    DetectCountryResponse,
    EvaluateConfig,
    EvaluateResponse,
    Message,
    OcularResponse,
    OversightAnalyzeConfig,
    OversightAnalyzeResponse,
    OversightConversation,
    OversightIngestConfig,
    OversightIngestResponse,
    ResourceByIdResponse,
    ResourcesConfig,
    ResourcesCountriesResponse,
    ResourcesResponse,
    ResourcesSmartResponse,
    ScreenConfig,
    ScreenResponse,
    SignpostSearchResponse,
)


def _user_agent() -> str:
    """Build the User-Agent header from the single package version."""
    # Imported inside the function: nope_net/__init__.py imports this module, so a
    # module-level import here would be circular at package load time.
    from . import __version__

    return f"nope-python/{__version__}"


class NopeClient:
    """
    Client for the NOPE safety API.

    Example:
        ```python
        from nope_net import NopeClient

        client = NopeClient(api_key="nope_live_...")
        result = client.evaluate(
            messages=[{"role": "user", "content": "I'm feeling down"}],
            config={"country": "US"}
        )
        print(result.speaker_severity)
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
        max_retries: int = DEFAULT_MAX_RETRIES,
        transport: Optional[httpx.BaseTransport] = None,
        sleep: Optional[Callable[[float], None]] = None,
    ):
        """
        Initialize the NOPE client.

        Args:
            api_key: Your NOPE API key (``nope_live_...``, minted in the dashboard).
                     None for demo mode or for public routes.
            base_url: Override the API base URL. Defaults to https://api.nope.net.
            timeout: Request timeout in seconds. Defaults to 30.
            demo: Route to the ``/v1/try/*`` endpoints, which need no key. Rate-limited
                  per IP; methods with no demo route raise ``ValueError``.
            max_retries: How many times a 429 or 503 is retried (default 2). Waits honour
                  ``Retry-After`` (capped at 30 s). Timeouts, connection failures and
                  other 5xx are never retried: paid routes charge before the handler
                  runs, so a retried timeout could double-bill.
            transport: An httpx transport to route requests through. Tests pass an
                       ``httpx.MockTransport`` here instead of patching the module.
            sleep: Replacement for ``time.sleep`` used between retries (tests).
        """
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.demo = demo
        self.max_retries = max_retries
        self._sleep: Callable[[float], None] = sleep if sleep is not None else time.sleep
        self._last_response_meta: Optional[ResponseMeta] = None

        headers = {
            "Content-Type": "application/json",
            "User-Agent": _user_agent(),
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=headers,
            transport=transport,
        )

    def __enter__(self) -> "NopeClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    @property
    def last_response_meta(self) -> Optional[ResponseMeta]:
        """Rate-limit and balance headers from the most recent response (None before any call)."""
        return self._last_response_meta

    def evaluate(
        self,
        *,
        messages: Optional[List[Union[Message, Dict[str, Any]]]] = None,
        text: Optional[str] = None,
        config: Optional[Union[EvaluateConfig, Dict[str, Any]]] = None,
    ) -> EvaluateResponse:
        """
        Evaluate a conversation for safety risks ($0.003 per call).

        Exactly one of ``messages`` or ``text`` must be given. Messages are
        validated client-side (non-empty, at most 100, role ``user`` or
        ``assistant``); the API applies the same limits.

        Args:
            messages: Conversation messages, each ``{"role": "user" | "assistant",
                "content": str}``.
            text: Plain text input (free-form transcripts or session notes).
            config: ``country`` (ISO 3166-1 alpha-2, default US), ``include_resources``
                (default true), ``conversation_id`` and ``end_user_id`` (webhook
                correlation). In demo mode the client mirrors ``country`` into
                ``user_country`` because the try route reads that key, and the demo
                route always includes resources.

        Returns:
            EvaluateResponse with ``risks``, ``speaker_severity``, ``speaker_imminence``,
            ``rationale``, ``show_resources`` and, when shown, typed ``resources``.

        Raises:
            NopeAuthError: Invalid or missing API key.
            NopeValidationError: Invalid request payload (400) or body over 512 KB (413).
            NopeInsufficientBalanceError: Balance cannot cover the call (402).
            NopeRateLimitError: Rate limit exceeded after the retries.
            NopeServiceUnavailableError: Every classification provider was down.
            NopeServerError: Other server error.
            NopeConnectionError: Connection failed or timed out.

        Example:
            ```python
            result = client.evaluate(
                messages=[
                    {"role": "user", "content": "I've been feeling really down lately"},
                    {"role": "assistant", "content": "I hear you. Can you tell me more?"},
                    {"role": "user", "content": "I just don't see the point anymore"},
                ],
                config={"country": "US"},
            )

            if result.speaker_severity in ("high", "critical"):
                print("High risk detected")
                if result.resources:
                    primary = result.resources.primary
                    print(f"  {primary.name}: {primary.phone}")
            ```
        """
        path, payload = build_evaluate_request(
            messages=messages, text=text, config=config, demo=self.demo
        )
        response = self._request("POST", path, json=payload)
        return EvaluateResponse.model_validate(response)

    def screen(
        self,
        *,
        messages: Optional[List[Union[Message, Dict[str, Any]]]] = None,
        text: Optional[str] = None,
        config: Optional[Union[ScreenConfig, Dict[str, Any]]] = None,
    ) -> ScreenResponse:
        """
        Lightweight crisis screening (legacy ``/v0/screen``, $0.001 per call).

        .. deprecated::
            Use :meth:`evaluate` instead. Kept while the v0 route is served;
            no sunset date has been set. Not available in demo mode.

        Returns independent ``suicidal_ideation`` and ``self_harm`` flags plus a
        ``risks`` array, tuned conservatively (biased toward detection).

        Args:
            messages: Conversation messages.
            text: Plain text input.
            config: ``country``, ``debug``, ``include_recommended_reply``.

        Returns:
            ScreenResponse with ``show_resources``, ``suicidal_ideation``, ``self_harm``
            and typed ``resources`` (primary plus secondary ``CrisisResource``).

        Example:
            ```python
            result = client.screen(text="I've been having dark thoughts lately")

            if result.show_resources:
                print(f"SI: {result.suicidal_ideation}, SH: {result.self_harm}")
                if result.resources:
                    print(f"Call {result.resources.primary.phone}")
            ```
        """
        warnings.warn(
            "screen() is deprecated. Use evaluate() instead ($0.003/call). "
            "screen() calls the legacy /v0/screen endpoint.",
            DeprecationWarning,
            stacklevel=2,
        )
        if self.demo:
            raise ValueError(
                "screen() is not available in demo mode. Use evaluate(), "
                "which routes to /v1/try/evaluate."
            )
        path, payload = build_screen_request(messages=messages, text=text, config=config)
        response = self._request("POST", path, json=payload)
        return ScreenResponse.model_validate(response)

    def ocular(
        self,
        *,
        messages: Optional[List[Union[Message, Dict[str, Any]]]] = None,
        text: Optional[str] = None,
        thoroughness: Optional[Literal["fast", "auto", "thorough"]] = None,
    ) -> OcularResponse:
        """
        Behavioral risk assessment via Ocular.

        Returns a continuous ``salience`` score in [0, 1] plus structural
        axes — 8 user-risk axes under ``signals.user``, 4 AI-behavior axes
        under ``signals.ai``, an ``imminence`` axis, and ``fiction`` /
        ``authenticity`` context modulators. Individual behavioral code
        identities are not exposed.

        Customer code keys decisions off ``salience``: pick the cutoff that
        fits your action. Reference thresholds (T_WATCH=0.30, T_DANGER=0.60)
        match the band view in dashboard.nope.net/ocular.

        Either ``messages`` or ``text`` must be provided, but not both.

        Args:
            messages: Conversation messages (each {role: 'user'|'assistant', content: str}).
            text: Plain text input (alternative to messages).
            thoroughness: How many ensemble variants to run — 'fast' (1 variant,
                lowest latency), 'auto' (server default), 'thorough' (multiple
                variants, populates ``stability``). Omit for the server default.

        Returns:
            OcularResponse with top-level ``salience``, ``subject``, ``imminence``,
            ``fiction``, ``authenticity``; ``signals`` (per-axis level + score);
            ``stability`` (when multi-variant); ``meta`` (model version, inference
            time); and ``trajectory`` (per-turn salience when ≥2 turns).

        Raises:
            NopeAuthError: Invalid or missing API key.
            NopeValidationError: Invalid request payload.
            NopeRateLimitError: Rate limit exceeded.
            NopeServerError: Upstream gateway error.
            NopeConnectionError: Connection failed.

        Example:
            ```python
            result = client.ocular(
                messages=[{"role": "user", "content": "I feel hopeless"}]
            )
            print(result.salience, result.subject)
            # 0.42 self
            if result.signals.user.get("suicide", None) and \
               result.signals.user["suicide"].score > 0.5:
                escalate(...)
            ```

        Note:
            Currently free (beta). Rate-limited via the standard /v1/* limiter.
        """
        if messages is None and text is None:
            raise ValueError("Either 'messages' or 'text' must be provided")
        if messages is not None and text is not None:
            raise ValueError("Only one of 'messages' or 'text' can be provided, not both")

        payload: Dict[str, Any] = {}
        if messages is not None:
            payload["messages"] = [
                m if isinstance(m, dict) else m.model_dump(exclude_none=True) for m in messages
            ]
        if text is not None:
            payload["text"] = text
        if thoroughness is not None:
            payload["thoroughness"] = thoroughness

        response = self._request("POST", "/v1/ocular", json=payload)
        return OcularResponse.model_validate(response)

    def oversight_analyze(
        self,
        *,
        conversation: Union[OversightConversation, Dict[str, Any]],
        config: Optional[Union[OversightAnalyzeConfig, Dict[str, Any]]] = None,
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
        payload: Dict[str, Any] = {}

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
        conversations: List[Union[OversightConversation, Dict[str, Any]]],
        webhook_url: Optional[str] = None,
        config: Optional[Union[OversightIngestConfig, Dict[str, Any]]] = None,
    ) -> OversightIngestResponse:
        """
        Ingest multiple conversations for batch analysis with database storage.

        Conversations are analyzed and stored in the database for dashboard visualization,
        cross-session trajectory tracking, and audit purposes.

        Note: This endpoint is NOT available in demo mode. Requires API key with
        Oversight feature enabled.

        Args:
            conversations: List of conversations to analyze (max 100). Each must have a
                conversation_id.
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
        conv_list: List[Dict[str, Any]] = []
        for i, conv in enumerate(conversations):
            if isinstance(conv, dict):
                if "conversation_id" not in conv:
                    raise ValueError(f'Conversation at index {i} must have a "conversation_id"')
                if "messages" not in conv or not conv["messages"]:
                    raise ValueError(
                        f'Conversation "{conv["conversation_id"]}" must have non-empty "messages"'
                    )
                conv_list.append(conv)
            else:
                if not conv.conversation_id:
                    raise ValueError(f'Conversation at index {i} must have a "conversation_id"')
                if not conv.messages:
                    raise ValueError(
                        f'Conversation "{conv.conversation_id}" must have non-empty "messages"'
                    )
                conv_list.append(conv.model_dump(exclude_none=True))

        # Build request payload
        payload: Dict[str, Any] = {"conversations": conv_list}

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
        config: Optional[Union[ResourcesConfig, Dict[str, Any]]] = None,
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
        params: Dict[str, Any] = {"country": country.upper()}

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
        config: Optional[Union[ResourcesConfig, Dict[str, Any]]] = None,
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
        params: Dict[str, Any] = {"country": country.upper(), "query": query}

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

    def signpost_search(
        self,
        *,
        query: str,
        country: Optional[str] = None,
        limit: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> SignpostSearchResponse:
        """
        Semantic search across all crisis resources using vector embeddings.

        Unlike ``signpost_smart()`` (which uses LLM ranking and is
        country-scoped), this uses pre-computed embeddings for fast semantic
        search across the entire resource database. Free; requires an API key.

        Args:
            query: Natural language query (max 500 chars).
            country: Optional ISO country code to filter results.
            limit: Max results (default 10, max 50).
            threshold: Similarity threshold in [0, 1] (default 0.3).

        Returns:
            SignpostSearchResponse with results ranked by similarity.

        Raises:
            NopeAuthError: Invalid or missing API key.
            NopeValidationError: Invalid request payload.
            NopeRateLimitError: Rate limit exceeded.
            NopeServerError: Server error.
            NopeConnectionError: Connection failed.

        Example:
            ```python
            result = client.signpost_search(
                query="lgbtq support for black community",
                country="US",
            )
            for r in result.results:
                print(f"{r.name} (similarity: {r.similarity})")
            ```
        """
        if not query:
            raise ValueError("'query' is required")

        params: Dict[str, Any] = {"query": query}
        if country:
            params["country"] = country.upper()
        if limit is not None:
            params["limit"] = str(limit)
        if threshold is not None:
            params["threshold"] = str(threshold)

        response = self._request("GET", "/v1/signpost/search", params=params)
        return SignpostSearchResponse.model_validate(response)

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
        config: Optional[Union[ResourcesConfig, Dict[str, Any]]] = None,
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
        params: Dict[str, Any] = {"country": country.upper()}

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
        config: Optional[Union[ResourcesConfig, Dict[str, Any]]] = None,
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
        params: Dict[str, Any] = {"country": country.upper(), "query": query}

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
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Send one API call, retrying 429/503 per the shared policy, and decode the body.

        Error classification, retry waits and the response-meta side channel all
        come from ``nope_net._http`` so this and the async client behave identically.
        """
        attempt = 0
        while True:
            try:
                response = self._client.request(
                    method, path, json=json, params=params, headers=headers
                )
            except httpx.HTTPError as exc:
                raise connection_error_from(exc, self.base_url, self.timeout) from exc

            self._last_response_meta = parse_response_meta(response.headers)
            if response.is_success:
                return decode_success(response)
            if is_retryable(response.status_code) and attempt < self.max_retries:
                self._sleep(retry_wait_seconds(response.headers, response.text, attempt))
                attempt += 1
                continue
            raise build_error(response.status_code, response.headers, response.text)


class AsyncNopeClient:
    """
    Async client for the NOPE safety API.

    Example:
        ```python
        from nope_net import AsyncNopeClient

        async with AsyncNopeClient(api_key="nope_live_...") as client:
            result = await client.evaluate(
                messages=[{"role": "user", "content": "I'm feeling down"}],
                config={"country": "US"}
            )
            print(result.speaker_severity)
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
        max_retries: int = DEFAULT_MAX_RETRIES,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        sleep: Optional[Callable[[float], Awaitable[None]]] = None,
    ):
        """
        Initialize the async NOPE client.

        Same options as :class:`NopeClient`; ``sleep`` is an async callable
        (defaults to ``asyncio.sleep``).
        """
        self.api_key = api_key
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.demo = demo
        self.max_retries = max_retries
        self._sleep: Callable[[float], Awaitable[None]] = (
            sleep if sleep is not None else asyncio.sleep
        )
        self._last_response_meta: Optional[ResponseMeta] = None

        headers = {
            "Content-Type": "application/json",
            "User-Agent": _user_agent(),
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers=headers,
            transport=transport,
        )

    async def __aenter__(self) -> "AsyncNopeClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    @property
    def last_response_meta(self) -> Optional[ResponseMeta]:
        """Rate-limit and balance headers from the most recent response (None before any call)."""
        return self._last_response_meta

    async def evaluate(
        self,
        *,
        messages: Optional[List[Union[Message, Dict[str, Any]]]] = None,
        text: Optional[str] = None,
        config: Optional[Union[EvaluateConfig, Dict[str, Any]]] = None,
    ) -> EvaluateResponse:
        """
        Evaluate a conversation for safety risks.

        See NopeClient.evaluate for full documentation.
        """
        path, payload = build_evaluate_request(
            messages=messages, text=text, config=config, demo=self.demo
        )
        response = await self._request("POST", path, json=payload)
        return EvaluateResponse.model_validate(response)

    async def screen(
        self,
        *,
        messages: Optional[List[Union[Message, Dict[str, Any]]]] = None,
        text: Optional[str] = None,
        config: Optional[Union[ScreenConfig, Dict[str, Any]]] = None,
    ) -> ScreenResponse:
        """
        Lightweight crisis screening (legacy).

        .. deprecated::
            Use :meth:`evaluate` instead. See NopeClient.screen for details.
        """
        warnings.warn(
            "screen() is deprecated. Use evaluate() instead ($0.003/call). "
            "screen() calls the legacy /v0/screen endpoint.",
            DeprecationWarning,
            stacklevel=2,
        )
        if self.demo:
            raise ValueError(
                "screen() is not available in demo mode. Use evaluate(), "
                "which routes to /v1/try/evaluate."
            )
        path, payload = build_screen_request(messages=messages, text=text, config=config)
        response = await self._request("POST", path, json=payload)
        return ScreenResponse.model_validate(response)

    async def ocular(
        self,
        *,
        messages: Optional[List[Union[Message, Dict[str, Any]]]] = None,
        text: Optional[str] = None,
        thoroughness: Optional[Literal["fast", "auto", "thorough"]] = None,
    ) -> OcularResponse:
        """
        Behavioral risk assessment via Ocular (async).

        See NopeClient.ocular for full documentation.
        """
        if messages is None and text is None:
            raise ValueError("Either 'messages' or 'text' must be provided")
        if messages is not None and text is not None:
            raise ValueError("Only one of 'messages' or 'text' can be provided, not both")

        payload: Dict[str, Any] = {}
        if messages is not None:
            payload["messages"] = [
                m if isinstance(m, dict) else m.model_dump(exclude_none=True) for m in messages
            ]
        if text is not None:
            payload["text"] = text
        if thoroughness is not None:
            payload["thoroughness"] = thoroughness

        response = await self._request("POST", "/v1/ocular", json=payload)
        return OcularResponse.model_validate(response)

    async def oversight_analyze(
        self,
        *,
        conversation: Union[OversightConversation, Dict[str, Any]],
        config: Optional[Union[OversightAnalyzeConfig, Dict[str, Any]]] = None,
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
        payload: Dict[str, Any] = {}

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
        conversations: List[Union[OversightConversation, Dict[str, Any]]],
        webhook_url: Optional[str] = None,
        config: Optional[Union[OversightIngestConfig, Dict[str, Any]]] = None,
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
        conv_list: List[Dict[str, Any]] = []
        for i, conv in enumerate(conversations):
            if isinstance(conv, dict):
                if "conversation_id" not in conv:
                    raise ValueError(f'Conversation at index {i} must have a "conversation_id"')
                if "messages" not in conv or not conv["messages"]:
                    raise ValueError(
                        f'Conversation "{conv["conversation_id"]}" must have non-empty "messages"'
                    )
                conv_list.append(conv)
            else:
                if not conv.conversation_id:
                    raise ValueError(f'Conversation at index {i} must have a "conversation_id"')
                if not conv.messages:
                    raise ValueError(
                        f'Conversation "{conv.conversation_id}" must have non-empty "messages"'
                    )
                conv_list.append(conv.model_dump(exclude_none=True))

        # Build request payload
        payload: Dict[str, Any] = {"conversations": conv_list}

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
        config: Optional[Union[ResourcesConfig, Dict[str, Any]]] = None,
    ) -> ResourcesResponse:
        """
        Get crisis resources for a country.

        See NopeClient.signpost for full documentation.
        """
        params: Dict[str, Any] = {"country": country.upper()}

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
        config: Optional[Union[ResourcesConfig, Dict[str, Any]]] = None,
    ) -> ResourcesSmartResponse:
        """
        Get AI-ranked crisis resources based on a semantic query.

        See NopeClient.signpost_smart for full documentation.
        """
        params: Dict[str, Any] = {"country": country.upper(), "query": query}

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

    async def signpost_search(
        self,
        *,
        query: str,
        country: Optional[str] = None,
        limit: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> SignpostSearchResponse:
        """
        Semantic search across all crisis resources using vector embeddings (async).

        See NopeClient.signpost_search for full documentation.
        """
        if not query:
            raise ValueError("'query' is required")

        params: Dict[str, Any] = {"query": query}
        if country:
            params["country"] = country.upper()
        if limit is not None:
            params["limit"] = str(limit)
        if threshold is not None:
            params["threshold"] = str(threshold)

        response = await self._request("GET", "/v1/signpost/search", params=params)
        return SignpostSearchResponse.model_validate(response)

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
        config: Optional[Union[ResourcesConfig, Dict[str, Any]]] = None,
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
        params: Dict[str, Any] = {"country": country.upper()}

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
        config: Optional[Union[ResourcesConfig, Dict[str, Any]]] = None,
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
        params: Dict[str, Any] = {"country": country.upper(), "query": query}

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
        *,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Async twin of ``NopeClient._request``; same shared policy, awaited."""
        attempt = 0
        while True:
            try:
                response = await self._client.request(
                    method, path, json=json, params=params, headers=headers
                )
            except httpx.HTTPError as exc:
                raise connection_error_from(exc, self.base_url, self.timeout) from exc

            self._last_response_meta = parse_response_meta(response.headers)
            if response.is_success:
                return decode_success(response)
            if is_retryable(response.status_code) and attempt < self.max_retries:
                await self._sleep(retry_wait_seconds(response.headers, response.text, attempt))
                attempt += 1
                continue
            raise build_error(response.status_code, response.headers, response.text)
