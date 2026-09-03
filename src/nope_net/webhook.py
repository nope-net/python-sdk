"""
Webhook verification and payload types.

NOPE signs every delivery with HMAC-SHA256 over ``"<timestamp>.<body>"`` and
sends ``X-NOPE-Signature: sha256=<hex>``, ``X-NOPE-Timestamp: <unix seconds>``,
``X-NOPE-Event``, ``X-NOPE-Delivery-ID`` and ``X-NOPE-Webhook-ID``. Pass the raw
request body (bytes or str) to :meth:`Webhook.verify_request`; that is the
supported input, since the signature covers the exact bytes the API sent.

Example:
    ```python
    from nope_net import Webhook, WebhookSignatureError, EvaluateAlertPayload

    @app.post("/webhooks/nope")
    def handle_webhook(request):
        try:
            verified = Webhook.verify_request(
                request.get_data(),
                request.headers,
                os.environ["NOPE_WEBHOOK_SECRET"],
            )
        except WebhookSignatureError:
            return {"error": "invalid signature"}, 401

        event = verified.payload
        if isinstance(event, EvaluateAlertPayload):
            print(event.risk_summary.overall_severity)
        return {"status": "ok"}, 200
    ```

Payload types are copied field for field from ``api/lib/webhooks/types.ts``;
unknown extra fields are kept (``extra="allow"``), so an additive change on the
API never breaks parsing.
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Annotated, Any, Dict, List, Literal, Mapping, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter

from .types import Imminence, Severity

# =============================================================================
# Event and payload types
# =============================================================================

WebhookEventType = Literal[
    "evaluate.alert",
    "oversight.alert",
    "oversight.ingestion.complete",
    "test.ping",
]

WebhookRiskLevel = Literal["none", "low", "medium", "high", "critical"]


class WebhookRiskSummary(BaseModel):
    """Risk summary on an ``evaluate.alert``."""

    model_config = {"extra": "allow"}

    overall_severity: Severity
    overall_imminence: Imminence
    primary_domain: str
    confidence: float
    primary_concerns: Union[str, List[str]]
    """Narrative concerns. The API type says string; the builder passes the
    evaluator's value through, which is a list of strings on the live wire."""


class WebhookDomainAssessment(BaseModel):
    """Per-domain assessment on an ``evaluate.alert``."""

    model_config = {"extra": "allow"}

    domain: str
    severity: Severity
    imminence: Imminence


class WebhookFlags(BaseModel):
    """Legal/safeguarding flags on an ``evaluate.alert``."""

    model_config = {"extra": "allow"}

    intimate_partner_violence: Optional[str] = None
    child_safeguarding: Optional[str] = None
    third_party_threat: bool


class WebhookResourceProvided(BaseModel):
    """A resource that was returned with the evaluate response."""

    model_config = {"extra": "allow"}

    name: str
    type: str
    country: str


class WebhookConversation(BaseModel):
    """Conversation content, included when the webhook has ``include_conversation``."""

    model_config = {"extra": "allow"}

    included: bool
    message_count: Optional[int] = None
    latest_user_message: Optional[str] = None
    truncated: Optional[bool] = None


class WebhookPayloadBase(BaseModel):
    """Envelope fields shared by every event."""

    model_config = {"extra": "allow"}

    event_id: str
    """Unique event ID (``evt_<32 hex>``) for idempotency."""

    timestamp: str
    """ISO 8601 creation time."""

    api_version: Literal["2025-01"]
    """Payload format version."""


class EvaluateAlertPayload(WebhookPayloadBase):
    """``evaluate.alert``: user risk from ``/v1/evaluate`` at or above the webhook's threshold."""

    event: Literal["evaluate.alert"]
    conversation_id: Optional[str] = None
    """Your ``config.conversation_id`` from the evaluate request."""
    user_id: Optional[str] = None
    """Your ``config.end_user_id`` from the evaluate request."""
    risk_summary: WebhookRiskSummary
    domains: List[WebhookDomainAssessment]
    flags: WebhookFlags
    resources_provided: List[WebhookResourceProvided]
    conversation: WebhookConversation


class OversightAlertBehavior(BaseModel):
    """One of the top behaviours on an ``oversight.alert`` (up to 5)."""

    model_config = {"extra": "allow"}

    code: str
    name: str
    severity: str
    category: str


class OversightAlertPayload(WebhookPayloadBase):
    """``oversight.alert``: concerning AI behaviour from analyze or ingest."""

    event: Literal["oversight.alert"]
    conversation_id: str
    concern: Literal["high", "critical"]
    trajectory: Literal["improving", "stable", "worsening"]
    summary: str
    behaviors: List[OversightAlertBehavior]
    agent_ids: Optional[List[str]] = None
    platform: Optional[str] = None
    user_is_minor: bool
    conversation: Optional[WebhookConversation] = None


class OversightIngestionConcerns(BaseModel):
    """Concern-level breakdown across an ingest batch."""

    model_config = {"extra": "allow"}

    none: int
    low: int
    medium: int
    high: int
    critical: int


class OversightIngestionTopBehavior(BaseModel):
    """A top behaviour across an ingest batch."""

    model_config = {"extra": "allow"}

    code: str
    name: str
    occurrence_count: int


class OversightIngestionCompletePayload(WebhookPayloadBase):
    """``oversight.ingestion.complete``: an ingest batch finished processing."""

    event: Literal["oversight.ingestion.complete"]
    ingestion_id: str
    conversations_total: int
    conversations_processed: int
    conversations_failed: int
    concerns: OversightIngestionConcerns
    top_behaviors: List[OversightIngestionTopBehavior]
    processing_time_ms: int


class TestPingPayload(WebhookPayloadBase):
    """``test.ping``: sent by ``client.webhooks.test(id)`` and the dashboard."""

    # Not a pytest test class, despite the name the API gave the event.
    __test__ = False

    event: Literal["test.ping"]
    message: str


WebhookPayload = Annotated[
    Union[
        EvaluateAlertPayload,
        OversightAlertPayload,
        OversightIngestionCompletePayload,
        TestPingPayload,
    ],
    Field(discriminator="event"),
]
"""Discriminated union of the four events, keyed on ``event``."""

_PAYLOAD_ADAPTER: TypeAdapter[Any] = TypeAdapter(WebhookPayload)


def parse_webhook_payload(data: Dict[str, Any]) -> Any:
    """Validate a decoded body into the matching payload model.

    Raises ``pydantic.ValidationError`` (a ``ValueError``) for an unknown
    ``event`` or a malformed body.
    """
    return _PAYLOAD_ADAPTER.validate_python(data)


# =============================================================================
# Errors and results
# =============================================================================


class WebhookSignatureError(Exception):
    """The signature, timestamp or secret did not check out."""


@dataclass(frozen=True)
class VerifiedWebhook:
    """Result of :meth:`Webhook.verify_request`."""

    payload: Any
    """One of the four payload models (``WebhookPayload``)."""

    event: str
    """Event type, from ``X-NOPE-Event`` (falls back to the payload's ``event``)."""

    event_id: Optional[str]
    """``X-NOPE-Delivery-ID``; use it to de-duplicate redeliveries."""

    webhook_id: Optional[str]
    """``X-NOPE-Webhook-ID``: which webhook configuration sent this."""


# =============================================================================
# Verification
# =============================================================================


def _serialize(payload: Union[str, bytes, Dict[str, Any]]) -> str:
    """The exact string that was signed.

    A dict is re-serialised the way the API serialises (compact separators,
    UTF-8 kept as-is). That reproduces the signed bytes only while key order
    survived the parse; pass the raw body when you can.
    """
    if isinstance(payload, bytes):
        return payload.decode("utf-8")
    if isinstance(payload, dict):
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return payload


def _hmac_hex(secret: str, timestamp: str, payload_string: str) -> str:
    message = f"{timestamp}.{payload_string}"
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


class Webhook:
    """Webhook verification and signing."""

    @staticmethod
    def verify(
        payload: Union[str, bytes, Dict[str, Any]],
        signature: Optional[str],
        timestamp: Optional[str],
        secret: str,
        *,
        max_age_seconds: int = 300,
    ) -> Any:
        """
        Verify a delivery and parse its payload.

        Args:
            payload: The raw request body (bytes or str) as received. A dict is
                accepted and re-serialised compactly with UTF-8 intact, which
                matches the API only while key order survived parsing.
            signature: ``X-NOPE-Signature`` header value (``sha256=`` prefix optional).
            timestamp: ``X-NOPE-Timestamp`` header value (unix seconds).
            secret: Your webhook signing secret (``whsec_...``).
            max_age_seconds: Reject deliveries older (or newer) than this. Default
                300. ``0`` disables the check.

        Returns:
            One of ``EvaluateAlertPayload``, ``OversightAlertPayload``,
            ``OversightIngestionCompletePayload`` or ``TestPingPayload``; branch
            with ``isinstance`` or on ``.event``.

        Raises:
            WebhookSignatureError: Missing header, bad timestamp, stale delivery,
                or signature mismatch.
            pydantic.ValidationError: The signature checked out but the body is not
                one of the four known events.
        """
        if not signature:
            raise WebhookSignatureError("Missing X-NOPE-Signature header")
        if not timestamp:
            raise WebhookSignatureError("Missing X-NOPE-Timestamp header")
        if not secret:
            raise WebhookSignatureError("Webhook secret is required")

        try:
            timestamp_num = int(timestamp)
        except ValueError:
            raise WebhookSignatureError("Invalid timestamp format") from None

        if max_age_seconds > 0:
            age = int(time.time()) - timestamp_num
            if age > max_age_seconds:
                raise WebhookSignatureError(
                    f"Timestamp too old: {age}s ago (max: {max_age_seconds}s)"
                )
            if age < -max_age_seconds:
                raise WebhookSignatureError(
                    f"Timestamp too far in future: {-age}s ahead (max: {max_age_seconds}s)"
                )

        payload_string = _serialize(payload)
        expected = _hmac_hex(secret, timestamp, payload_string)
        received = signature[7:] if signature.startswith("sha256=") else signature
        if not hmac.compare_digest(expected, received):
            raise WebhookSignatureError("Signature verification failed")

        data = payload if isinstance(payload, dict) else json.loads(payload_string)
        return parse_webhook_payload(data)

    @staticmethod
    def verify_request(
        body: Union[str, bytes],
        headers: Mapping[str, str],
        secret: str,
        *,
        max_age_seconds: int = 300,
    ) -> VerifiedWebhook:
        """
        Verify a delivery from the raw body and the request headers.

        Reads ``x-nope-signature``, ``x-nope-timestamp``, ``x-nope-event``,
        ``x-nope-delivery-id`` and ``x-nope-webhook-id`` case-insensitively, so
        any framework's header mapping works.

        Returns:
            :class:`VerifiedWebhook` with the parsed ``payload``, ``event``,
            ``event_id`` (delivery ID) and ``webhook_id``.
        """
        lowered = {str(k).lower(): v for k, v in headers.items()}
        payload = Webhook.verify(
            body,
            lowered.get("x-nope-signature"),
            lowered.get("x-nope-timestamp"),
            secret,
            max_age_seconds=max_age_seconds,
        )
        return VerifiedWebhook(
            payload=payload,
            event=lowered.get("x-nope-event") or payload.event,
            event_id=lowered.get("x-nope-delivery-id"),
            webhook_id=lowered.get("x-nope-webhook-id"),
        )

    @staticmethod
    def sign(
        payload: Union[str, bytes, Dict[str, Any]],
        secret: str,
        timestamp: Optional[int] = None,
    ) -> Dict[str, str]:
        """
        Sign a payload the way the API does (for tests and local tooling).

        Args:
            payload: Body to sign (str, bytes, or a dict serialised compactly with
                UTF-8 intact).
            secret: Signing secret.
            timestamp: Unix seconds (defaults to now).

        Returns:
            ``{"signature": "sha256=<hex>", "timestamp": "<unix seconds>"}``.
        """
        ts = timestamp if timestamp is not None else int(time.time())
        sig = _hmac_hex(secret, str(ts), _serialize(payload))
        return {"signature": f"sha256={sig}", "timestamp": str(ts)}
