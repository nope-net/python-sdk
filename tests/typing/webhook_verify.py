"""mypy --strict fixture: ``Webhook.verify`` returns the typed payload union.

On 4.0.0 ``verify()`` and ``VerifiedWebhook.payload`` were ``Any``, so
``return payload.event`` below trips strict's ``no-any-return`` and
``verified.delivery_id`` does not exist. Both pass on 4.0.1.
"""

from typing import Mapping, Optional

from nope_net import (
    EvaluateAlertPayload,
    TestPingPayload,
    Webhook,
    WebhookPayloadUnion,
    WebhookSignatureError,
)


def low_level(body: bytes, signature: str, timestamp: str, secret: str) -> str:
    payload: WebhookPayloadUnion = Webhook.verify(body, signature, timestamp, secret)
    if isinstance(payload, TestPingPayload):
        return payload.message
    if isinstance(payload, EvaluateAlertPayload):
        return payload.risk_summary.overall_severity
    return payload.event


def high_level(body: bytes, headers: Mapping[str, str], secret: str) -> Optional[str]:
    try:
        verified = Webhook.verify_request(body, headers, secret)
    except WebhookSignatureError:
        return None
    seen: Optional[str] = verified.delivery_id
    if seen is None:
        return verified.payload.event_id
    return verified.payload.event
