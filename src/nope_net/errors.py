"""
NOPE SDK exceptions.

Every error raised from an HTTP response carries:

- ``status_code``: the HTTP status.
- ``code``: the machine string from the body's ``error`` field when it looks
  like a code (``^[a-z_]+$``), or the body's ``code`` field when present.
  ``None`` when the body only carried a sentence.
- ``message``: ``body.message`` when present, else ``body.error``, else the
  HTTP status text.
- ``response_body``: the raw response text.
- ``body``: the parsed JSON object when the response was one, else ``None``.
- ``details``: the body's extra keys on a validation error; ``{}`` on every
  other error, so ``err.details`` never raises ``AttributeError``.

Client-side validation and demo-mode refusals raise ``NopeValidationError``
before any request is sent: ``status_code`` is ``None``, ``code`` is
``invalid_request`` or ``not_available_in_demo``, and the class is also a
``ValueError``.

The status-to-class mapping lives in ``nope_net._http.build_error`` and is shared
by the sync and async clients.
"""

from typing import Any, Dict, Optional


class NopeError(Exception):
    """Base exception for all NOPE SDK errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        response_body: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.response_body = response_body
        self.body = body
        """The response decoded as a JSON object, or ``None`` when it was not one."""
        self.details: Dict[str, Any] = {}
        """Extra keys from the body; filled by ``NopeValidationError``, ``{}`` elsewhere."""

    def __str__(self) -> str:
        parts = []
        if self.status_code:
            parts.append(f"[{self.status_code}]")
        if self.code:
            parts.append(f"{self.code}:")
        parts.append(self.message)
        return " ".join(parts)


class NopeAuthError(NopeError):
    """HTTP 401: the API key is missing, malformed, revoked, or expired."""

    def __init__(
        self,
        message: str = "Invalid or missing API key",
        *,
        code: Optional[str] = None,
        response_body: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message, status_code=401, code=code, response_body=response_body, body=body
        )


class NopeValidationError(NopeError, ValueError):
    """The request was rejected: HTTP 400 or 413, or a client-side check.

    ``details`` holds every extra key the body carried beside ``error`` and
    ``message`` (``max_bytes`` on 413, ``max_messages``, ``max_content_length``,
    ``invalid_scopes``, ``hint``, and the Oversight validator's own ``details``).

    Raised before any request is sent when the SDK's own validation fails
    (``code`` ``invalid_request``) or a demo client calls a method with no
    ``/v1/try/*`` route (``code`` ``not_available_in_demo``); ``status_code``
    is ``None`` and ``details`` is empty in both cases. The class is also a
    ``ValueError``, so ``except ValueError`` keeps working.
    """

    def __init__(
        self,
        message: str = "Invalid request",
        *,
        status_code: Optional[int] = 400,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        response_body: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message, status_code=status_code, code=code, response_body=response_body, body=body
        )
        self.details = details or {}


class NopeInsufficientBalanceError(NopeError):
    """HTTP 402: the account balance cannot cover this call.

    ``balance_mills`` and ``required_mills`` are in mills (1 mill = $0.001).
    ``per_conversation_mills`` and ``conversations`` are set only by
    ``/v1/oversight/ingest``, which prices per conversation.
    """

    def __init__(
        self,
        message: str = "Insufficient balance",
        *,
        code: Optional[str] = None,
        balance_mills: Optional[float] = None,
        required_mills: Optional[float] = None,
        formatted_current: Optional[str] = None,
        formatted_required: Optional[str] = None,
        topup_url: Optional[str] = None,
        per_conversation_mills: Optional[float] = None,
        conversations: Optional[int] = None,
        response_body: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message, status_code=402, code=code, response_body=response_body, body=body
        )
        self.balance_mills = balance_mills
        self.required_mills = required_mills
        self.formatted_current = formatted_current
        self.formatted_required = formatted_required
        self.topup_url = topup_url
        self.per_conversation_mills = per_conversation_mills
        self.conversations = conversations


class NopeFeatureError(NopeError):
    """HTTP 403 for a gated feature.

    Two body shapes reach this class. A feature gate (``feature`` plus
    ``required_access``, for Oversight and Ocular) and a paid-plan gate
    (``upgrade_url``), which is reported as ``feature = "paid_plan"``.
    """

    def __init__(
        self,
        message: str = "Feature not enabled for this account",
        *,
        code: Optional[str] = None,
        feature: Optional[str] = None,
        required_access: Optional[str] = None,
        upgrade_url: Optional[str] = None,
        response_body: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message, status_code=403, code=code, response_body=response_body, body=body
        )
        self.feature = feature
        self.required_access = required_access
        self.upgrade_url = upgrade_url

    def __str__(self) -> str:
        base = super().__str__()
        if self.feature:
            return f"{base} (feature: {self.feature})"
        return base


class NopeNotFoundError(NopeError):
    """HTTP 404: the resource, webhook, or route does not exist."""

    def __init__(
        self,
        message: str = "Not found",
        *,
        code: Optional[str] = None,
        response_body: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message, status_code=404, code=code, response_body=response_body, body=body
        )


class NopeRateLimitError(NopeError):
    """HTTP 429: rate limit exceeded.

    ``retry_after`` is in seconds (from the ``Retry-After`` header, else the
    body's ``retry_after_seconds``). ``limit``, ``remaining`` and ``reset``
    (epoch milliseconds) mirror the ``X-RateLimit-*`` headers.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        code: Optional[str] = None,
        retry_after: Optional[float] = None,
        limit: Optional[int] = None,
        remaining: Optional[int] = None,
        reset: Optional[int] = None,
        response_body: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message, status_code=429, code=code, response_body=response_body, body=body
        )
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.reset = reset

    def __str__(self) -> str:
        base = super().__str__()
        if self.retry_after:
            return f"{base} (retry after {self.retry_after}s)"
        return base


class NopeServerError(NopeError):
    """HTTP 5xx other than 503.

    ``retry_after`` is set only when the response carried a ``Retry-After``
    header or ``retry_after_seconds`` in the body. The client never retries
    these itself: paid routes charge before the handler runs and refund on
    failure, so a blind retry after a timeout could double-bill.
    """

    def __init__(
        self,
        message: str = "Server error",
        *,
        status_code: int = 500,
        code: Optional[str] = None,
        retry_after: Optional[float] = None,
        response_body: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message, status_code=status_code, code=code, response_body=response_body, body=body
        )
        self.retry_after = retry_after


class NopeServiceUnavailableError(NopeServerError):
    """HTTP 503: a dependency or every classification provider is down.

    ``retry_after`` is in seconds. The client retries 503 (and 429) up to
    ``max_retries`` times before raising this.
    """

    def __init__(
        self,
        message: str = "Service unavailable",
        *,
        code: Optional[str] = None,
        retry_after: Optional[float] = None,
        response_body: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message,
            status_code=503,
            code=code,
            retry_after=retry_after,
            response_body=response_body,
            body=body,
        )


class NopeConnectionError(NopeError):
    """The request never produced an HTTP response (connect failure, timeout)."""

    def __init__(
        self,
        message: str = "Failed to connect to NOPE API",
        *,
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.original_error = original_error
