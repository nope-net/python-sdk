"""
Webhook Utilities

Verify incoming webhook signatures and parse payloads.

Example:
    ```python
    from nope_net import Webhook, WebhookPayload

    @app.post('/webhooks/nope')
    def handle_webhook(request):
        try:
            event = Webhook.verify(
                payload=request.body,
                signature=request.headers.get('x-nope-signature'),
                timestamp=request.headers.get('x-nope-timestamp'),
                secret=os.environ['NOPE_WEBHOOK_SECRET']
            )

            print(f"Received {event.event}: {event.risk_summary.overall_severity}")
            return {'status': 'ok'}, 200
        except WebhookSignatureError as e:
            print(f"Webhook verification failed: {e}")
            return {'error': 'Invalid signature'}, 401
    ```
"""

import hashlib
import hmac
import json
import time
from typing import List, Literal, Optional, Union

from pydantic import BaseModel

from .types import Severity, Imminence


# =============================================================================
# Webhook Types
# =============================================================================

WebhookEventType = Literal["risk.elevated", "risk.critical", "test.ping"]
WebhookRiskLevel = Literal["none", "low", "medium", "high", "critical"]


class WebhookRiskSummary(BaseModel):
    """Risk summary in webhook payload."""

    overall_severity: Severity
    overall_imminence: Imminence
    primary_domain: str
    confidence: float
    primary_concerns: str


class WebhookDomainAssessment(BaseModel):
    """Domain assessment in webhook payload."""

    domain: str
    severity: Severity
    imminence: Imminence


class WebhookFlags(BaseModel):
    """Legal/safeguarding flags in webhook payload."""

    intimate_partner_violence: Optional[str] = None
    child_safeguarding: Optional[str] = None
    third_party_threat: bool


class WebhookResourceProvided(BaseModel):
    """Resource reference in webhook payload."""

    name: str
    type: str
    country: str


class WebhookConversation(BaseModel):
    """Conversation info in webhook payload."""

    included: bool
    message_count: Optional[int] = None
    latest_user_message: Optional[str] = None
    truncated: Optional[bool] = None


class WebhookPayload(BaseModel):
    """
    Webhook payload received from NOPE.

    This is the body of the POST request sent to your webhook endpoint.
    """

    event: WebhookEventType
    """Event type: risk.elevated, risk.critical, or test.ping"""

    event_id: str
    """Unique event ID for idempotency"""

    timestamp: str
    """ISO 8601 timestamp when event was created"""

    api_version: Literal["2025-01"]
    """API version for payload format"""

    conversation_id: Optional[str] = None
    """Your conversation_id (if provided in evaluate request)"""

    user_id: Optional[str] = None
    """Your end_user_id (if provided in evaluate request)"""

    risk_summary: WebhookRiskSummary
    """Risk assessment summary"""

    domains: List[WebhookDomainAssessment]
    """Per-domain risk assessments"""

    flags: WebhookFlags
    """Legal/safeguarding flags"""

    resources_provided: List[WebhookResourceProvided]
    """Crisis resources that were provided"""

    conversation: WebhookConversation
    """Conversation content (if include_conversation enabled)"""


# =============================================================================
# Errors
# =============================================================================


class WebhookSignatureError(Exception):
    """Error thrown when webhook signature verification fails."""

    pass


# =============================================================================
# Webhook Verification
# =============================================================================


class Webhook:
    """Webhook verification and parsing utilities."""

    @staticmethod
    def verify(
        payload: Union[str, bytes, dict],
        signature: Optional[str],
        timestamp: Optional[str],
        secret: str,
        *,
        max_age_seconds: int = 300,
    ) -> WebhookPayload:
        """
        Verify webhook signature and parse payload.

        Args:
            payload: Raw request body (string, bytes, or dict)
            signature: X-NOPE-Signature header value
            timestamp: X-NOPE-Timestamp header value
            secret: Your webhook signing secret
            max_age_seconds: Maximum age of timestamp in seconds (default: 300 = 5 minutes).
                            Set to 0 to disable timestamp checking (not recommended).

        Returns:
            Parsed and verified WebhookPayload

        Raises:
            WebhookSignatureError: If verification fails

        Example:
            ```python
            event = Webhook.verify(
                payload=request.body,
                signature=request.headers.get('x-nope-signature'),
                timestamp=request.headers.get('x-nope-timestamp'),
                secret=secret
            )
            ```
        """
        # Validate inputs
        if not signature:
            raise WebhookSignatureError("Missing X-NOPE-Signature header")
        if not timestamp:
            raise WebhookSignatureError("Missing X-NOPE-Timestamp header")
        if not secret:
            raise WebhookSignatureError("Webhook secret is required")

        # Parse timestamp
        try:
            timestamp_num = int(timestamp)
        except ValueError:
            raise WebhookSignatureError("Invalid timestamp format")

        # Check timestamp freshness
        if max_age_seconds > 0:
            now = int(time.time())
            age = now - timestamp_num

            if age > max_age_seconds:
                raise WebhookSignatureError(
                    f"Timestamp too old: {age}s ago (max: {max_age_seconds}s)"
                )
            if age < -max_age_seconds:
                raise WebhookSignatureError(
                    f"Timestamp too far in future: {-age}s ahead (max: {max_age_seconds}s)"
                )

        # Normalize payload to string
        if isinstance(payload, bytes):
            payload_string = payload.decode("utf-8")
        elif isinstance(payload, dict):
            payload_string = json.dumps(payload, separators=(",", ":"))
        else:
            payload_string = payload

        # Compute expected signature
        message = f"{timestamp}.{payload_string}"
        expected = hmac.new(
            secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        # Extract signature value (remove sha256= prefix if present)
        received = signature
        if received.startswith("sha256="):
            received = received[7:]

        # Constant-time comparison
        if not hmac.compare_digest(expected, received):
            raise WebhookSignatureError("Signature verification failed")

        # Parse and return payload
        if isinstance(payload, dict):
            return WebhookPayload(**payload)
        else:
            return WebhookPayload(**json.loads(payload_string))

    @staticmethod
    def sign(
        payload: Union[str, bytes, dict],
        secret: str,
        timestamp: Optional[int] = None,
    ) -> dict:
        """
        Generate a signature for testing purposes.

        Args:
            payload: Payload to sign (string, bytes, or dict)
            secret: Signing secret
            timestamp: Unix timestamp in seconds (defaults to now)

        Returns:
            Dict with 'signature' and 'timestamp' keys

        Example:
            ```python
            result = Webhook.sign(payload, secret)
            signature = result['signature']
            timestamp = result['timestamp']
            ```
        """
        ts = timestamp if timestamp is not None else int(time.time())

        # Normalize payload to string
        if isinstance(payload, bytes):
            payload_string = payload.decode("utf-8")
        elif isinstance(payload, dict):
            payload_string = json.dumps(payload, separators=(",", ":"))
        else:
            payload_string = payload

        message = f"{ts}.{payload_string}"
        sig = hmac.new(
            secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        return {
            "signature": f"sha256={sig}",
            "timestamp": str(ts),
        }
