"""
NOPE SDK Client

Main client for interacting with the NOPE API.
"""

import asyncio
import time
import warnings
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Union,
)

import httpx

from ._generated.signpost_enums import Population, ServiceScope
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
from ._namespaces import AsyncBillingClient, AsyncWebhooksClient, BillingClient, WebhooksClient
from ._requests import (
    build_evaluate_request,
    build_ocular_request,
    build_oversight_analyze_request,
    build_oversight_ingest_request,
    build_screen_request,
    build_signpost_params,
    build_signpost_search_params,
    build_signpost_smart_params,
    not_available_in_demo,
)
from .types import (
    DetectCountryResponse,
    EvaluateConfig,
    EvaluateResponse,
    Message,
    OcularDemoResponse,
    OcularResponse,
    OversightAnalyzeConfig,
    OversightAnalyzeResponse,
    OversightBehaviorFilter,
    OversightConversation,
    OversightDemoAnalyzeResponse,
    OversightIngestConfig,
    OversightIngestResponse,
    ScreenConfig,
    ScreenResponse,
    SignpostByIdResponse,
    SignpostConfig,
    SignpostCountriesResponse,
    SignpostResponse,
    SignpostSearchResponse,
    SignpostSmartConfig,
    SignpostSmartResponse,
)

RESOURCES_SUNSET = "2027-01-01"


def _warn_deprecated_resources(name: str, replacement: str) -> None:
    """One warning text for the four /v1/resources/* wrappers, shared by both clients."""
    warnings.warn(
        f"{name}() is deprecated (sunset {RESOURCES_SUNSET}; use {replacement}()). "
        "It calls the deprecated /v1/resources route, which is served with "
        "Deprecation and Sunset headers until then.",
        DeprecationWarning,
        stacklevel=3,
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
                  per IP; methods with no demo route raise ``NopeValidationError``
                  (``code`` ``not_available_in_demo``).
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
        self.webhooks = WebhooksClient(self)
        """Webhook management: ``client.webhooks.create/list/get/update/delete/...``."""
        self.billing = BillingClient(self)
        """Billing: ``client.billing.balance/usage/usage_history/pricing/topup``."""

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
        messages: Optional[Sequence[Union[Message, Mapping[str, Any]]]] = None,
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
                "content": str}`` or a ``Message``. Any sequence (list, tuple) of
                dicts, mappings or models is accepted and sent as a JSON array.
            text: Plain text input (free-form transcripts or session notes). A note
                about someone else yields ``speaker_severity`` ``none`` with a
                ``subject`` ``other`` risk; check ``risks[].subject`` or
                :func:`has_third_party_risk` for third-party risk.
            config: ``country`` (ISO 3166-1 alpha-2, default US), ``include_resources``
                (default true), ``conversation_id`` and ``end_user_id`` (webhook
                correlation). The demo route reads ``country`` too (the client also
                sends it as ``user_country``, which the route ignores) and always
                includes resources.

        Returns:
            EvaluateResponse with ``risks``, ``speaker_severity``, ``speaker_imminence``,
            ``rationale``, ``show_resources`` and, when shown, typed ``resources``.

        Raises:
            NopeAuthError: Invalid or missing API key.
            NopeValidationError: A client-side check failed (``status_code`` None,
                ``code`` ``invalid_request``), the API rejected the payload (400), or
                the body was over 512 KB (413).
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
        messages: Optional[Sequence[Union[Message, Mapping[str, Any]]]] = None,
        text: Optional[str] = None,
        config: Optional[Union[ScreenConfig, Dict[str, Any]]] = None,
    ) -> ScreenResponse:
        """
        Lightweight crisis screening (legacy ``/v0/screen``, $0.001 per call).

        .. deprecated::
            Use :meth:`evaluate` instead. The ``/v0/screen`` route is served with
            Deprecation and Sunset headers and sunsets on 2027-01-01, the date the
            runtime warning names. Not available in demo mode.

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
            "screen() calls the legacy /v0/screen endpoint, which carries a sunset of 2027-01-01.",
            DeprecationWarning,
            stacklevel=2,
        )
        if self.demo:
            raise not_available_in_demo(
                "screen() is not available in demo mode. Use evaluate(), "
                "which routes to /v1/try/evaluate."
            )
        path, payload = build_screen_request(messages=messages, text=text, config=config)
        response = self._request("POST", path, json=payload)
        return ScreenResponse.model_validate(response)

    def ocular(
        self,
        *,
        messages: Optional[Sequence[Union[Message, Mapping[str, Any]]]] = None,
        text: Optional[str] = None,
        thoroughness: Optional[Literal["fast", "auto", "thorough"]] = None,
        per_turn: Optional[bool] = None,
        trajectory_stride: Optional[int] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> OcularResponse:
        """
        Behavioral risk assessment via Ocular ($0.0001 per call).

        Returns a continuous ``salience`` score in [0, 1] plus structural axes:
        8 user-risk axes under ``signals.user``, 4 AI-behavior axes under
        ``signals.ai``, an ``imminence`` axis, and the ``fiction`` and
        ``authenticity`` context modulators. Individual behavioral code
        identities are not exposed on the customer wire.

        Customer code keys decisions off ``salience``: pick the cutoff that
        fits your action. Reference thresholds (T_WATCH=0.30, T_DANGER=0.60)
        match the band view in dashboard.nope.net/ocular.

        Exactly one of ``messages`` or ``text`` must be given.

        Args:
            messages: Conversation messages (each {role: 'user'|'assistant', content: str}).
            text: Plain text input (alternative to messages).
            thoroughness: 'fast' (1 variant, lowest latency), 'auto' (server default),
                'thorough' (multiple variants, populates ``stability``).
            per_turn: Return ``trajectory`` (one entry per scored turn: the 0-based
                ``turn`` index into ``messages``, ``salience`` and ``signals_by_axis``
                with ``ai_``-prefixed AI axes plus ``genuine``/``fiction``) and, on
                ``/v1/ocular``, ``trajectory_shape``. Off by default; the price is
                unchanged.
            trajectory_stride: Score every Nth turn counting back from the last
                (1..64). The server default is 3, so a three-message conversation
                yields one scored turn (``turn`` 2); pass 1 to score every turn.
            user_id: Opaque identifier stored in your usage metadata for dashboard
                analytics (1..256 chars). Never forwarded to the model host.
            session_id: As ``user_id``.
            agent_id: As ``user_id``.

        Returns:
            OcularResponse; in demo mode an ``OcularDemoResponse`` that adds
            ``heads`` and ``detail`` keyed by public family head names. The demo
            route ignores ``thoroughness`` and the identity fields, and returns
            ``trajectory`` but never ``trajectory_shape``.

        Raises:
            NopeValidationError: Neither or both inputs, a bad role,
                ``trajectory_stride`` outside 1..64, or an identity field outside
                1..256 characters (client-side, ``status_code`` None).
            NopeFeatureError: Ocular is not enabled for this account.
            NopeServerError: Upstream gateway error.

        Example:
            ```python
            result = client.ocular(
                messages=[{"role": "user", "content": "I feel hopeless"}],
                per_turn=True,
            )
            print(result.salience, result.subject)
            if result.signals.user["suicide"].score > 0.5:
                escalate(...)
            for turn in result.trajectory or []:
                print(turn.turn, turn.salience, turn.signals_by_axis)
            ```

        Note:
            ``meta.windowed`` and ``meta.windows`` are always present on the
            current build (``false`` and ``1`` for un-windowed input).
        """
        path, payload = build_ocular_request(
            messages=messages,
            text=text,
            thoroughness=thoroughness,
            per_turn=per_turn,
            trajectory_stride=trajectory_stride,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            demo=self.demo,
        )
        response = self._request("POST", path, json=payload)
        if self.demo:
            return OcularDemoResponse.model_validate(response)
        return OcularResponse.model_validate(response)

    def oversight_analyze(
        self,
        conversation: Union[OversightConversation, Mapping[str, Any]],
        *,
        bot_context: Optional[str] = None,
        config: Optional[Union[OversightAnalyzeConfig, Dict[str, Any]]] = None,
        behaviors: Optional[Union[OversightBehaviorFilter, Dict[str, Any]]] = None,
    ) -> Union[OversightAnalyzeResponse, OversightDemoAnalyzeResponse]:
        """
        Analyze one conversation for harmful AI behaviours ($0.10 per call).

        Synchronous; nothing is stored. Use :meth:`oversight_ingest` for
        persistent storage and the dashboard. Turn numbers in the result are
        1-based and count assistant turns.

        Args:
            conversation: ``conversation_id``, ``messages`` (role ``user``, ``assistant``
                or ``system``; optional ``message_id``, ``timestamp``, ``agent_id``,
                ``agent_version``, ``context``) and optional ``metadata``.
            bot_context: Free-form description of the bot or persona ("customer
                support bot for an airline"). The API merges it into the conversation
                metadata and builds a calibration block from it in the analysis
                prompt.
            config: ``strategy`` (``single``/``sliding``, auto by length), ``mode``
                (``full``/``fast``), ``include_raw_xml``, ``model``. Fast mode
                returns no ``summary``/``pattern_assessment``, an empty
                ``turn_analysis`` and the constant trajectory ``stable``.
            behaviors: ``enabled`` xor ``disabled`` (behaviour codes), ``min_severity``,
                ``categories``. Validated client-side; the API returns 400 for an
                unknown code or category.

        Returns:
            ``OversightAnalyzeResponse`` (``result``, ``strategy``, ``strategy_reason``)
            or, in demo mode, ``OversightDemoAnalyzeResponse`` (``mode``, ``result``,
            ``try_endpoint``). The demo route ignores ``strategy`` and ``model`` and
            caps input at 20 messages.

        Raises:
            NopeValidationError: Empty messages, bad role, ``enabled`` and
                ``disabled`` both non-empty, or an invalid ``min_severity``
                (client-side, ``status_code`` None).
            NopeFeatureError: Oversight is not enabled for this account.
            NopeInsufficientBalanceError: Balance cannot cover the call.

        Example:
            ```python
            result = client.oversight_analyze(
                {
                    "conversation_id": "conv_123",
                    "messages": [
                        {"role": "user", "content": "I want to end it all"},
                        {"role": "assistant", "content": "I understand how you feel..."},
                    ],
                    "metadata": {"user_is_minor": True},
                },
                config={"mode": "fast"},
                behaviors={"min_severity": "medium"},
            )

            print(f"Concern: {result.result.overall_concern}")
            for behavior in result.result.detected_behaviors:
                print(f"  {behavior.code}: {behavior.severity} -> {behavior.recommendation}")
            ```
        """
        path, payload = build_oversight_analyze_request(
            conversation=conversation,
            bot_context=bot_context,
            config=config,
            behaviors=behaviors,
            demo=self.demo,
        )
        response = self._request("POST", path, json=payload)
        if self.demo:
            return OversightDemoAnalyzeResponse.model_validate(response)
        return OversightAnalyzeResponse.model_validate(response)

    def oversight_ingest(
        self,
        *,
        conversations: Sequence[Union[OversightConversation, Mapping[str, Any]]],
        webhook_url: Optional[str] = None,
        config: Optional[Union[OversightIngestConfig, Dict[str, Any]]] = None,
    ) -> OversightIngestResponse:
        """
        Ingest up to 300 conversations for analysis with database storage.

        Each conversation is analyzed and stored for the dashboard, cross-session
        trajectory tracking and audit. Billing is $0.10 per conversation, deducted
        before analysis. The route is synchronous: ``status`` is ``complete`` or
        ``failed`` when it returns. Not available in demo mode.

        Args:
            conversations: Conversations (at most 300), each with a ``conversation_id``
                and non-empty ``messages``; any sequence of dicts, mappings or
                ``OversightConversation`` models. The request body is capped at
                512 KB, so a batch near the count limit must consist of short
                conversations.
            webhook_url: Legacy per-request callback. The API POSTs an unsigned
                ``{event: 'ingestion_complete', timestamp, ingestion_id,
                conversations_processed, errors_count, high_concern_count}`` here when
                the batch completes. The signed ``oversight.ingestion.complete`` event
                goes to webhooks registered with ``client.webhooks``.
            config: ``model``.

        Returns:
            OversightIngestResponse with per-conversation results and errors.

        Raises:
            NopeValidationError: Demo mode, empty list, more than 300
                conversations, or a conversation without
                ``conversation_id``/``messages`` (client-side, ``status_code`` None).
            NopeFeatureError: Oversight is not enabled for this account.
            NopeInsufficientBalanceError: Balance cannot cover 100 mills per conversation.

        Example:
            ```python
            result = client.oversight_ingest(
                conversations=[
                    {"conversation_id": "conv_001", "messages": [...]},
                    {"conversation_id": "conv_002", "messages": [...]},
                ],
                webhook_url="https://api.example.com/webhooks/nope",
            )

            print(f"{result.conversations_processed}/{result.conversations_received}")
            print(result.dashboard_url)
            ```
        """
        if self.demo:
            raise not_available_in_demo(
                "Oversight ingest is not available in demo mode. Use an API key."
            )
        path, payload = build_oversight_ingest_request(
            conversations=conversations, webhook_url=webhook_url, config=config
        )
        response = self._request("POST", path, json=payload)
        return OversightIngestResponse.model_validate(response)

    # =========================================================================
    # Signpost (crisis resources)
    # =========================================================================

    def signpost(
        self,
        country: str,
        *,
        config: Optional[Union[SignpostConfig, Dict[str, Any]]] = None,
        scopes: Optional[List[ServiceScope]] = None,
        populations: Optional[List[Population]] = None,
        subdivisions: Optional[List[str]] = None,
        limit: Optional[int] = None,
        urgent: Optional[bool] = None,
    ) -> SignpostResponse:
        """
        Crisis resources for a country (free, requires an API key, no LLM).

        Filters may be passed at the top level or under ``config``; a top-level
        value wins. For LLM-ranked picks use :meth:`signpost_smart`. Not
        available in demo mode.

        Args:
            country: ISO 3166-1 alpha-2 code (e.g. "US", "GB").
            config: ``SignpostConfig`` or dict with the same keys as below.
            scopes: Service scopes from ``nope_net.SERVICE_SCOPES`` (e.g. "suicide",
                "domestic_violence"). With scopes the response also carries
                ``primary`` and ``secondary``.
            populations: Populations from ``nope_net.POPULATIONS`` (e.g. "youth").
            subdivisions: ISO 3166-2 codes within the country (e.g. "GB-SCT").
            limit: Maximum resources (the API clamps to 10).
            urgent: Only 24/7 resources.

        Returns:
            SignpostResponse with ``resources`` (and ``primary``/``secondary`` when
            scopes were given). Branch on ``resource.type`` to tell a line from a
            service.

        Raises:
            NopeValidationError: Demo mode (``code`` ``not_available_in_demo``), or
                an unknown scope or population (400, ``details.invalid_scopes``).

        Example:
            ```python
            result = client.signpost("US", scopes=["suicide"], urgent=True)
            for resource in result.resources:
                print(f"{resource.name}: {resource.phone}")
            ```
        """
        if self.demo:
            raise not_available_in_demo("signpost() is not available in demo mode. Use an API key.")
        params = build_signpost_params(
            country=country,
            config=config,
            scopes=scopes,
            populations=populations,
            subdivisions=subdivisions,
            limit=limit,
            urgent=urgent,
        )
        response = self._request("GET", "/v1/signpost", params=params)
        return SignpostResponse.model_validate(response)

    def signpost_smart(
        self,
        country: str,
        query: str,
        *,
        config: Optional[Union[SignpostSmartConfig, Dict[str, Any]]] = None,
    ) -> SignpostSmartResponse:
        """
        LLM-ranked crisis resources for a situation ($0.001 per call).

        Ranks the country's pool against ``query`` and returns up to 5 picks,
        each with a one-line ``why``. In demo mode routes to
        ``/v1/try/signpost/smart`` (free, rate-limited per IP).

        Args:
            country: ISO 3166-1 alpha-2 code.
            query: Natural-language description of the situation (max 500 chars).
            config: ``scopes``, ``populations``, ``limit`` (up to 5).

        Returns:
            SignpostSmartResponse with ``ranked[]`` of ``{rank, resource, why}``;
            ``message`` is set when the country pool is empty.

        Example:
            ```python
            result = client.signpost_smart("US", "teen struggling with eating disorder")
            for item in result.ranked:
                print(f"{item.rank}. {item.resource.name}: {item.why}")
            ```
        """
        params = build_signpost_smart_params(country=country, query=query, config=config)
        endpoint = "/v1/try/signpost/smart" if self.demo else "/v1/signpost/smart"
        response = self._request("GET", endpoint, params=params)
        return SignpostSmartResponse.model_validate(response)

    def signpost_search(
        self,
        *,
        query: str,
        country: Optional[str] = None,
        limit: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> SignpostSearchResponse:
        """
        Semantic search across the whole resource directory (free, requires an API key).

        Uses pre-computed embeddings rather than LLM ranking, and is not
        country-scoped unless ``country`` is given. Rows come back in the
        directory's own shape (:class:`SignpostSearchResult`). Not available
        in demo mode.

        Args:
            query: Natural language query (max 500 chars).
            country: Optional ISO country code filter.
            limit: Max results (default 10, max 50).
            threshold: Similarity threshold in [0, 1] (default 0.3).

        Example:
            ```python
            result = client.signpost_search(query="lgbtq youth support", country="GB")
            for row in result.results:
                print(f"{row.name} ({row.similarity:.2f}): {row.phone}")
            ```
        """
        if self.demo:
            raise not_available_in_demo(
                "signpost_search() is not available in demo mode. Use an API key."
            )
        params = build_signpost_search_params(
            query=query, country=country, limit=limit, threshold=threshold
        )
        response = self._request("GET", "/v1/signpost/search", params=params)
        return SignpostSearchResponse.model_validate(response)

    def signpost_by_id(self, resource_id: str) -> SignpostByIdResponse:
        """
        One crisis resource by directory UUID (public, no key needed).

        Every database-backed resource carries ``id`` (basic, smart, search and
        evaluate results); the API's hard-coded fallback registry does not.

        Raises:
            NopeValidationError: Malformed UUID.
            NopeNotFoundError: No such resource.
        """
        response = self._request("GET", f"/v1/signpost/{resource_id}")
        return SignpostByIdResponse.model_validate(response)

    def signpost_countries(self) -> SignpostCountriesResponse:
        """List the countries with resources (public, no key needed)."""
        response = self._request("GET", "/v1/signpost/countries")
        return SignpostCountriesResponse.model_validate(response)

    def detect_country(self, country_hint: Optional[str] = None) -> DetectCountryResponse:
        """
        Detect the caller's country from proxy geo headers (public, no key needed).

        The route reads only headers a proxy injects (Cloudflare ``cf-ipcountry``,
        Netlify/Vercel ``x-country``/``x-vercel-ip-country``). The direct
        api.nope.net deployment carries none, so a direct call returns the miss
        shape (``detected`` False) with HTTP 200. Behind such a proxy it works.

        Args:
            country_hint: Sent as ``x-country`` so the route echoes it back; useful
                when your own edge already knows the country.

        Example:
            ```python
            detected = client.detect_country()
            if detected.detected:
                print(detected.country_code, detected.subdivision_code)
            ```
        """
        headers = {"x-country": country_hint.upper()} if country_hint else None
        response = self._request("GET", "/v1/signpost/detect-country", headers=headers)
        return DetectCountryResponse.model_validate(response)

    # =========================================================================
    # Deprecated /v1/resources/* twins (sunset 2027-01-01; use signpost*)
    # =========================================================================

    def resources(
        self,
        country: str,
        *,
        config: Optional[Union[SignpostConfig, Dict[str, Any]]] = None,
        scopes: Optional[List[ServiceScope]] = None,
        populations: Optional[List[Population]] = None,
        subdivisions: Optional[List[str]] = None,
        limit: Optional[int] = None,
        urgent: Optional[bool] = None,
    ) -> SignpostResponse:
        """Deprecated twin of :meth:`signpost` on ``/v1/resources`` (sunset 2027-01-01)."""
        _warn_deprecated_resources("resources", "signpost")
        params = build_signpost_params(
            country=country,
            config=config,
            scopes=scopes,
            populations=populations,
            subdivisions=subdivisions,
            limit=limit,
            urgent=urgent,
        )
        response = self._request("GET", "/v1/resources", params=params)
        return SignpostResponse.model_validate(response)

    def resources_smart(
        self,
        country: str,
        query: str,
        *,
        config: Optional[Union[SignpostSmartConfig, Dict[str, Any]]] = None,
    ) -> SignpostSmartResponse:
        """Deprecated twin of :meth:`signpost_smart` on ``/v1/resources/smart``."""
        _warn_deprecated_resources("resources_smart", "signpost_smart")
        params = build_signpost_smart_params(country=country, query=query, config=config)
        endpoint = "/v1/try/resources/smart" if self.demo else "/v1/resources/smart"
        response = self._request("GET", endpoint, params=params)
        return SignpostSmartResponse.model_validate(response)

    def resource_by_id(self, resource_id: str) -> SignpostByIdResponse:
        """Deprecated twin of :meth:`signpost_by_id` on ``/v1/resources/:id``."""
        _warn_deprecated_resources("resource_by_id", "signpost_by_id")
        response = self._request("GET", f"/v1/resources/{resource_id}")
        return SignpostByIdResponse.model_validate(response)

    def resources_countries(self) -> SignpostCountriesResponse:
        """Deprecated twin of :meth:`signpost_countries` on ``/v1/resources/countries``."""
        _warn_deprecated_resources("resources_countries", "signpost_countries")
        response = self._request("GET", "/v1/resources/countries")
        return SignpostCountriesResponse.model_validate(response)

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
        self.webhooks = AsyncWebhooksClient(self)
        self.billing = AsyncBillingClient(self)

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
        messages: Optional[Sequence[Union[Message, Mapping[str, Any]]]] = None,
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
        messages: Optional[Sequence[Union[Message, Mapping[str, Any]]]] = None,
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
            "screen() calls the legacy /v0/screen endpoint, which carries a sunset of 2027-01-01.",
            DeprecationWarning,
            stacklevel=2,
        )
        if self.demo:
            raise not_available_in_demo(
                "screen() is not available in demo mode. Use evaluate(), "
                "which routes to /v1/try/evaluate."
            )
        path, payload = build_screen_request(messages=messages, text=text, config=config)
        response = await self._request("POST", path, json=payload)
        return ScreenResponse.model_validate(response)

    async def ocular(
        self,
        *,
        messages: Optional[Sequence[Union[Message, Mapping[str, Any]]]] = None,
        text: Optional[str] = None,
        thoroughness: Optional[Literal["fast", "auto", "thorough"]] = None,
        per_turn: Optional[bool] = None,
        trajectory_stride: Optional[int] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> OcularResponse:
        """
        Behavioral risk assessment via Ocular (async).

        See NopeClient.ocular for full documentation.
        """
        path, payload = build_ocular_request(
            messages=messages,
            text=text,
            thoroughness=thoroughness,
            per_turn=per_turn,
            trajectory_stride=trajectory_stride,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            demo=self.demo,
        )
        response = await self._request("POST", path, json=payload)
        if self.demo:
            return OcularDemoResponse.model_validate(response)
        return OcularResponse.model_validate(response)

    async def oversight_analyze(
        self,
        conversation: Union[OversightConversation, Mapping[str, Any]],
        *,
        bot_context: Optional[str] = None,
        config: Optional[Union[OversightAnalyzeConfig, Dict[str, Any]]] = None,
        behaviors: Optional[Union[OversightBehaviorFilter, Dict[str, Any]]] = None,
    ) -> Union[OversightAnalyzeResponse, OversightDemoAnalyzeResponse]:
        """
        Analyze one conversation for harmful AI behaviours.

        See NopeClient.oversight_analyze for full documentation.
        """
        path, payload = build_oversight_analyze_request(
            conversation=conversation,
            bot_context=bot_context,
            config=config,
            behaviors=behaviors,
            demo=self.demo,
        )
        response = await self._request("POST", path, json=payload)
        if self.demo:
            return OversightDemoAnalyzeResponse.model_validate(response)
        return OversightAnalyzeResponse.model_validate(response)

    async def oversight_ingest(
        self,
        *,
        conversations: Sequence[Union[OversightConversation, Mapping[str, Any]]],
        webhook_url: Optional[str] = None,
        config: Optional[Union[OversightIngestConfig, Dict[str, Any]]] = None,
    ) -> OversightIngestResponse:
        """
        Ingest up to 300 conversations for analysis with database storage.

        See NopeClient.oversight_ingest for full documentation.
        """
        if self.demo:
            raise not_available_in_demo(
                "Oversight ingest is not available in demo mode. Use an API key."
            )
        path, payload = build_oversight_ingest_request(
            conversations=conversations, webhook_url=webhook_url, config=config
        )
        response = await self._request("POST", path, json=payload)
        return OversightIngestResponse.model_validate(response)

    # =========================================================================
    # Signpost (crisis resources)
    # =========================================================================

    async def signpost(
        self,
        country: str,
        *,
        config: Optional[Union[SignpostConfig, Dict[str, Any]]] = None,
        scopes: Optional[List[ServiceScope]] = None,
        populations: Optional[List[Population]] = None,
        subdivisions: Optional[List[str]] = None,
        limit: Optional[int] = None,
        urgent: Optional[bool] = None,
    ) -> SignpostResponse:
        """
        Crisis resources for a country (free, requires an API key, no LLM). See NopeClient for full
        documentation.
        """
        if self.demo:
            raise not_available_in_demo("signpost() is not available in demo mode. Use an API key.")
        params = build_signpost_params(
            country=country,
            config=config,
            scopes=scopes,
            populations=populations,
            subdivisions=subdivisions,
            limit=limit,
            urgent=urgent,
        )
        response = await self._request("GET", "/v1/signpost", params=params)
        return SignpostResponse.model_validate(response)

    async def signpost_smart(
        self,
        country: str,
        query: str,
        *,
        config: Optional[Union[SignpostSmartConfig, Dict[str, Any]]] = None,
    ) -> SignpostSmartResponse:
        """
        LLM-ranked crisis resources for a situation ($0.001 per call). See NopeClient for full
        documentation.
        """
        params = build_signpost_smart_params(country=country, query=query, config=config)
        endpoint = "/v1/try/signpost/smart" if self.demo else "/v1/signpost/smart"
        response = await self._request("GET", endpoint, params=params)
        return SignpostSmartResponse.model_validate(response)

    async def signpost_search(
        self,
        *,
        query: str,
        country: Optional[str] = None,
        limit: Optional[int] = None,
        threshold: Optional[float] = None,
    ) -> SignpostSearchResponse:
        """
        Semantic search across the whole resource directory (free, requires an API key). See
        NopeClient for full documentation.
        """
        if self.demo:
            raise not_available_in_demo(
                "signpost_search() is not available in demo mode. Use an API key."
            )
        params = build_signpost_search_params(
            query=query, country=country, limit=limit, threshold=threshold
        )
        response = await self._request("GET", "/v1/signpost/search", params=params)
        return SignpostSearchResponse.model_validate(response)

    async def signpost_by_id(self, resource_id: str) -> SignpostByIdResponse:
        """
        One crisis resource by directory UUID (public, no key needed). See NopeClient for full
        documentation.
        """
        response = await self._request("GET", f"/v1/signpost/{resource_id}")
        return SignpostByIdResponse.model_validate(response)

    async def signpost_countries(self) -> SignpostCountriesResponse:
        """List the countries with resources (public, no key needed)."""
        response = await self._request("GET", "/v1/signpost/countries")
        return SignpostCountriesResponse.model_validate(response)

    async def detect_country(self, country_hint: Optional[str] = None) -> DetectCountryResponse:
        """
        Detect the caller's country from proxy geo headers (public, no key needed). See NopeClient
        for full documentation.
        """
        headers = {"x-country": country_hint.upper()} if country_hint else None
        response = await self._request("GET", "/v1/signpost/detect-country", headers=headers)
        return DetectCountryResponse.model_validate(response)

    # =========================================================================
    # Deprecated /v1/resources/* twins (sunset 2027-01-01; use signpost*)
    # =========================================================================

    async def resources(
        self,
        country: str,
        *,
        config: Optional[Union[SignpostConfig, Dict[str, Any]]] = None,
        scopes: Optional[List[ServiceScope]] = None,
        populations: Optional[List[Population]] = None,
        subdivisions: Optional[List[str]] = None,
        limit: Optional[int] = None,
        urgent: Optional[bool] = None,
    ) -> SignpostResponse:
        """Deprecated twin of :meth:`signpost` on ``/v1/resources`` (sunset 2027-01-01)."""
        _warn_deprecated_resources("resources", "signpost")
        params = build_signpost_params(
            country=country,
            config=config,
            scopes=scopes,
            populations=populations,
            subdivisions=subdivisions,
            limit=limit,
            urgent=urgent,
        )
        response = await self._request("GET", "/v1/resources", params=params)
        return SignpostResponse.model_validate(response)

    async def resources_smart(
        self,
        country: str,
        query: str,
        *,
        config: Optional[Union[SignpostSmartConfig, Dict[str, Any]]] = None,
    ) -> SignpostSmartResponse:
        """Deprecated twin of :meth:`signpost_smart` on ``/v1/resources/smart``."""
        _warn_deprecated_resources("resources_smart", "signpost_smart")
        params = build_signpost_smart_params(country=country, query=query, config=config)
        endpoint = "/v1/try/resources/smart" if self.demo else "/v1/resources/smart"
        response = await self._request("GET", endpoint, params=params)
        return SignpostSmartResponse.model_validate(response)

    async def resource_by_id(self, resource_id: str) -> SignpostByIdResponse:
        """Deprecated twin of :meth:`signpost_by_id` on ``/v1/resources/:id``."""
        _warn_deprecated_resources("resource_by_id", "signpost_by_id")
        response = await self._request("GET", f"/v1/resources/{resource_id}")
        return SignpostByIdResponse.model_validate(response)

    async def resources_countries(self) -> SignpostCountriesResponse:
        """Deprecated twin of :meth:`signpost_countries` on ``/v1/resources/countries``."""
        _warn_deprecated_resources("resources_countries", "signpost_countries")
        response = await self._request("GET", "/v1/resources/countries")
        return SignpostCountriesResponse.model_validate(response)

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
