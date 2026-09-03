"""``VerifiedWebhook.delivery_id`` and the typed payload union.

``delivery_id`` is the ``X-NOPE-Delivery-ID`` header; ``event_id`` keeps
returning the same value for 4.0.0 callers, while ``payload.event_id`` is the
payload's own id. ``Webhook.verify()`` returns ``WebhookPayloadUnion``, the
plain union the discriminated ``WebhookPayload`` wraps.
"""

from typing import Dict, get_args

from nope_net import (
    EvaluateAlertPayload,
    OversightAlertPayload,
    OversightIngestionCompletePayload,
    TestPingPayload,
    VerifiedWebhook,
    Webhook,
    WebhookPayloadUnion,
)
from tests.conftest import load_fixture


def _signed_headers(secret: str, body: str, event: str) -> Dict[str, str]:
    signed = Webhook.sign(body, secret)
    return {
        "X-NOPE-Signature": signed["signature"],
        "X-NOPE-Timestamp": signed["timestamp"],
        "X-NOPE-Event": event,
    }


def test_verify_request_with_delivery_header() -> None:
    fx = load_fixture("webhooks/test.ping.json")
    headers = _signed_headers(fx["secret"], fx["body"], "test.ping")
    headers["X-NOPE-Delivery-ID"] = "dlv_local_1"
    headers["X-NOPE-Webhook-ID"] = "wh_local_1"

    verified = Webhook.verify_request(fx["body"], headers, fx["secret"])

    assert verified.delivery_id == "dlv_local_1"
    assert verified.event_id == "dlv_local_1"
    assert verified.payload.event_id == fx["payload"]["event_id"]
    assert verified.payload.event_id != verified.delivery_id
    assert verified.webhook_id == "wh_local_1"
    assert isinstance(verified.payload, TestPingPayload)


def test_verify_request_without_delivery_header() -> None:
    fx = load_fixture("webhooks/test.ping.json")
    headers = _signed_headers(fx["secret"], fx["body"], "test.ping")

    verified = Webhook.verify_request(fx["body"], headers, fx["secret"])

    assert verified.delivery_id is None
    assert verified.event_id is None
    assert verified.webhook_id is None
    assert verified.payload.event_id == fx["payload"]["event_id"]


def test_live_fixture_delivery_id_is_distinct_from_payload_event_id() -> None:
    """The API sends the payload's event_id as X-NOPE-Delivery-ID (signature.ts)."""
    for event in ("evaluate.alert", "oversight.alert", "oversight.ingestion.complete", "test.ping"):
        fx = load_fixture(f"webhooks/{event}.json")
        verified = Webhook.verify_request(
            fx["body"], fx["headers"], fx["secret"], max_age_seconds=0
        )
        assert verified.delivery_id == fx["headers"]["x-nope-delivery-id"]
        assert verified.delivery_id != verified.payload.event_id


def test_event_id_only_construction_keeps_working() -> None:
    """4.0.0 callers that build the dataclass themselves still get both names."""
    payload = TestPingPayload(
        event="test.ping",
        event_id="evt_1",
        timestamp="2026-09-03T00:55:00.000Z",
        api_version="2025-01",
        message="m",
    )
    legacy = VerifiedWebhook(payload=payload, event="test.ping", event_id="dlv_9", webhook_id=None)
    assert legacy.delivery_id == "dlv_9"
    assert legacy.event_id == "dlv_9"

    explicit = VerifiedWebhook(
        payload=payload, event="test.ping", event_id="dlv_9", webhook_id=None, delivery_id="dlv_9"
    )
    assert explicit == legacy


def test_payload_union_alias_names_the_four_models() -> None:
    assert set(get_args(WebhookPayloadUnion)) == {
        EvaluateAlertPayload,
        OversightAlertPayload,
        OversightIngestionCompletePayload,
        TestPingPayload,
    }
