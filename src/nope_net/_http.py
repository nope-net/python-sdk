"""Shared HTTP plumbing for the sync and async clients.

Everything that decides what a response means lives here, once: error
classification (``build_error``), the retry policy (``retry_wait_seconds``),
transport-failure wrapping (``connection_error_from``) and the response-meta
side channel (``parse_response_meta``). The two clients only differ in whether
they ``await``.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Union

import httpx

from .errors import (
    NopeAuthError,
    NopeConnectionError,
    NopeError,
    NopeFeatureError,
    NopeInsufficientBalanceError,
    NopeNotFoundError,
    NopeRateLimitError,
    NopeServerError,
    NopeServiceUnavailableError,
    NopeValidationError,
)

DEFAULT_MAX_RETRIES = 2
RETRYABLE_STATUSES = frozenset({429, 503})
MAX_RETRY_WAIT_SECONDS = 30.0

_CODE_PATTERN = re.compile(r"^[a-z_]+$")

HeaderMapping = Union[Mapping[str, str], httpx.Headers]


# =============================================================================
# Response meta side channel
# =============================================================================


@dataclass(frozen=True)
class RateLimitMeta:
    """``X-RateLimit-Limit`` / ``-Remaining`` / ``-Reset`` (reset is epoch milliseconds)."""

    limit: Optional[int]
    remaining: Optional[int]
    reset: Optional[int]


@dataclass(frozen=True)
class BalanceMeta:
    """``X-Balance-Mills`` and ``X-Cost-Mills``; present only on paid routes."""

    balance_mills: Optional[float]
    cost_mills: Optional[float]


@dataclass(frozen=True)
class ResponseMeta:
    """Headers from the last response the client received.

    ``rate_limit`` is ``None`` when no ``X-RateLimit-*`` header was present and
    ``balance`` is ``None`` off the paid routes.
    """

    rate_limit: Optional[RateLimitMeta]
    balance: Optional[BalanceMeta]


def _as_headers(headers: HeaderMapping) -> httpx.Headers:
    if isinstance(headers, httpx.Headers):
        return headers
    return httpx.Headers(dict(headers))


def _int_header(headers: httpx.Headers, name: str) -> Optional[int]:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _float_header(headers: httpx.Headers, name: str) -> Optional[float]:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def parse_response_meta(headers: HeaderMapping) -> ResponseMeta:
    """Build the ``ResponseMeta`` side channel from response headers."""
    h = _as_headers(headers)
    rate_limit: Optional[RateLimitMeta] = None
    if any(
        name in h for name in ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset")
    ):
        rate_limit = RateLimitMeta(
            limit=_int_header(h, "x-ratelimit-limit"),
            remaining=_int_header(h, "x-ratelimit-remaining"),
            reset=_int_header(h, "x-ratelimit-reset"),
        )
    balance: Optional[BalanceMeta] = None
    if "x-balance-mills" in h or "x-cost-mills" in h:
        balance = BalanceMeta(
            balance_mills=_float_header(h, "x-balance-mills"),
            cost_mills=_float_header(h, "x-cost-mills"),
        )
    return ResponseMeta(rate_limit=rate_limit, balance=balance)


# =============================================================================
# Error classification
# =============================================================================


def _decode_body(text: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _retry_after(headers: httpx.Headers, body: Dict[str, Any]) -> Optional[float]:
    """Seconds to wait: ``Retry-After`` header first, then ``retry_after_seconds``."""
    from_header = _float_header(headers, "retry-after")
    if from_header is not None:
        return from_header
    from_body = body.get("retry_after_seconds")
    if isinstance(from_body, (int, float)) and not isinstance(from_body, bool):
        return float(from_body)
    return None


def _optional_number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _optional_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _optional_str(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def build_error(status_code: int, headers: HeaderMapping, text: str) -> NopeError:
    """Map a non-2xx response to the exception the client raises.

    Pure: takes the status, headers and raw body, returns the exception instance
    (the caller raises it). Shared by ``NopeClient`` and ``AsyncNopeClient``.
    """
    h = _as_headers(headers)
    body = _decode_body(text)

    error_field = body.get("error")
    error_str = error_field if isinstance(error_field, str) else None

    code: Optional[str] = None
    explicit_code = body.get("code")
    if isinstance(explicit_code, str) and explicit_code:
        code = explicit_code
    elif error_str is not None and _CODE_PATTERN.match(error_str):
        code = error_str

    message_field = body.get("message")
    if isinstance(message_field, str) and message_field:
        message = message_field
    elif error_str:
        message = error_str
    else:
        message = httpx.codes.get_reason_phrase(status_code) or f"HTTP {status_code}"

    if status_code in (400, 413):
        details = {k: v for k, v in body.items() if k not in ("error", "message")}
        return NopeValidationError(
            message,
            status_code=status_code,
            code=code,
            details=details,
            response_body=text,
        )

    if status_code == 401:
        return NopeAuthError(message, code=code, response_body=text)

    if status_code == 402:
        balance = body.get("balance")
        balance = balance if isinstance(balance, dict) else {}
        return NopeInsufficientBalanceError(
            message,
            code=code,
            balance_mills=_optional_number(balance.get("current_mills")),
            required_mills=_optional_number(balance.get("required_mills")),
            formatted_current=_optional_str(balance.get("formatted_current")),
            formatted_required=_optional_str(balance.get("formatted_required")),
            topup_url=_optional_str(body.get("topup_url")),
            per_conversation_mills=_optional_number(balance.get("per_conversation_mills")),
            conversations=_optional_int(balance.get("conversations")),
            response_body=text,
        )

    if status_code == 403:
        feature = _optional_str(body.get("feature"))
        upgrade_url = _optional_str(body.get("upgrade_url"))
        if feature:
            return NopeFeatureError(
                message,
                code=code,
                feature=feature,
                required_access=_optional_str(body.get("required_access")),
                upgrade_url=upgrade_url,
                response_body=text,
            )
        if upgrade_url:
            return NopeFeatureError(
                message,
                code=code,
                feature="paid_plan",
                upgrade_url=upgrade_url,
                response_body=text,
            )
        return NopeError(message, status_code=403, code=code, response_body=text)

    if status_code == 404:
        return NopeNotFoundError(message, code=code, response_body=text)

    if status_code == 429:
        return NopeRateLimitError(
            message,
            code=code,
            retry_after=_retry_after(h, body),
            limit=_optional_int(body.get("limit")) or _int_header(h, "x-ratelimit-limit"),
            remaining=(
                _optional_int(body.get("remaining"))
                if "remaining" in body
                else _int_header(h, "x-ratelimit-remaining")
            ),
            reset=_optional_int(body.get("reset")) or _int_header(h, "x-ratelimit-reset"),
            response_body=text,
        )

    if status_code == 503:
        return NopeServiceUnavailableError(
            message,
            code=code,
            retry_after=_retry_after(h, body),
            response_body=text,
        )

    if status_code >= 500:
        return NopeServerError(
            message,
            status_code=status_code,
            code=code,
            retry_after=_retry_after(h, body),
            response_body=text,
        )

    return NopeError(message, status_code=status_code, code=code, response_body=text)


# =============================================================================
# Retry policy
# =============================================================================


def is_retryable(status_code: int) -> bool:
    """Only 429 and 503 are retried: both are raised before any charge is made."""
    return status_code in RETRYABLE_STATUSES


def retry_wait_seconds(headers: HeaderMapping, text: str, attempt: int) -> float:
    """Seconds to sleep before retry number ``attempt`` (0-based).

    ``Retry-After`` header, else body ``retry_after_seconds``, else
    1s doubling per attempt; every wait is capped at 30 seconds.
    """
    hinted = _retry_after(_as_headers(headers), _decode_body(text))
    wait = hinted if hinted is not None else float(2**attempt)
    return min(max(wait, 0.0), MAX_RETRY_WAIT_SECONDS)


# =============================================================================
# Transport failures
# =============================================================================


def connection_error_from(
    exc: httpx.HTTPError, base_url: str, timeout: float
) -> NopeConnectionError:
    """Wrap an httpx transport failure. Timeouts are never retried (double-bill risk)."""
    if isinstance(exc, httpx.ConnectError):
        return NopeConnectionError(f"Failed to connect to {base_url}", original_error=exc)
    if isinstance(exc, httpx.TimeoutException):
        return NopeConnectionError(f"Request timed out after {timeout}s", original_error=exc)
    return NopeConnectionError(f"HTTP error: {exc}", original_error=exc)


def decode_success(response: httpx.Response) -> Any:
    """Decode a 2xx body. Every API route returns JSON."""
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise NopeError(
            "Response was not valid JSON",
            status_code=response.status_code,
            response_body=response.text,
        ) from exc
