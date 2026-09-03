"""Webhook.verify / verify_request / sign against the API-signed fixtures.

Each fixture under tests/fixtures/webhooks/ carries the secret, the exact
headers the API sent, the byte-exact signed body, and the parsed payload.
"""

import json
import time
from typing import Any, Dict

import pytest

from nope_net import (
    EvaluateAlertPayload,
    OversightAlertPayload,
    OversightIngestionCompletePayload,
    TestPingPayload,
    Webhook,
    WebhookSignatureError,
    parse_webhook_payload,
)
from tests.conftest import load_fixture

EVENTS = ["evaluate.alert", "oversight.alert", "oversight.ingestion.complete", "test.ping"]
PAYLOAD_CLASSES = {
    "evaluate.alert": EvaluateAlertPayload,
    "oversight.alert": OversightAlertPayload,
    "oversight.ingestion.complete": OversightIngestionCompletePayload,
    "test.ping": TestPingPayload,
}


def _fixture(event: str) -> Dict[str, Any]:
    return load_fixture(f"webhooks/{event}.json")


@pytest.mark.parametrize("event", EVENTS)
def test_raw_string_path_verifies_each_event(event: str) -> None:
    fx = _fixture(event)
    payload = Webhook.verify(
        fx["body"],
        fx["headers"]["x-nope-signature"],
        fx["headers"]["x-nope-timestamp"],
        fx["secret"],
        max_age_seconds=0,
    )

    assert isinstance(payload, PAYLOAD_CLASSES[event])
    assert payload.event == event
    assert payload.event_id == fx["payload"]["event_id"]
    assert payload.api_version == "2025-01"
    assert payload.model_dump(mode="json", exclude_unset=True) == fx["payload"]


@pytest.mark.parametrize("event", EVENTS)
def test_bytes_path_verifies_each_event(event: str) -> None:
    fx = _fixture(event)
    payload = Webhook.verify(
        fx["body"].encode("utf-8"),
        fx["headers"]["x-nope-signature"],
        fx["headers"]["x-nope-timestamp"],
        fx["secret"],
        max_age_seconds=0,
    )
    assert payload.event == event


@pytest.mark.parametrize("event", EVENTS)
def test_verify_request_reads_headers_case_insensitively(event: str) -> None:
    fx = _fixture(event)
    headers = {k.upper(): v for k, v in fx["headers"].items()}
    verified = Webhook.verify_request(fx["body"], headers, fx["secret"], max_age_seconds=0)

    assert isinstance(verified.payload, PAYLOAD_CLASSES[event])
    assert verified.event_id == fx["headers"]["x-nope-delivery-id"]
    assert verified.webhook_id == "wh_fixture_0001"
    assert verified.event == event


def test_object_path_verifies_non_ascii_evaluate_alert() -> None:
    """The evaluate.alert body carries accented characters and curly quotes on purpose."""
    fx = _fixture("evaluate.alert")
    assert any(ord(ch) > 127 for ch in fx["body"])

    payload = Webhook.verify(
        fx["payload"],
        fx["headers"]["x-nope-signature"],
        fx["headers"]["x-nope-timestamp"],
        fx["secret"],
        max_age_seconds=0,
    )

    assert isinstance(payload, EvaluateAlertPayload)
    assert payload.risk_summary.primary_concerns == [
        "Passive ideation — “I don’t see the point anymore”",
        "Hopelessness",
    ]
    assert payload.resources_provided[0].name == "Línea de Prevención del Suicidio"
    assert payload.conversation.included is True


def test_sign_matches_api_signature_for_non_ascii_object() -> None:
    fx = _fixture("evaluate.alert")
    signed = Webhook.sign(
        fx["payload"], fx["secret"], timestamp=int(fx["headers"]["x-nope-timestamp"])
    )
    assert signed["signature"] == fx["headers"]["x-nope-signature"]
    assert signed["timestamp"] == fx["headers"]["x-nope-timestamp"]


def test_sign_then_verify_round_trip_object() -> None:
    payload = {
        "event": "test.ping",
        "event_id": "evt_x",
        "timestamp": "2026-09-03T00:55:00.000Z",
        "api_version": "2025-01",
        "message": "héllo — ping",
    }
    signed = Webhook.sign(payload, "whsec_" + "ab" * 32)
    parsed = Webhook.verify(payload, signed["signature"], signed["timestamp"], "whsec_" + "ab" * 32)
    assert isinstance(parsed, TestPingPayload)
    assert parsed.message == "héllo — ping"


def test_tampered_body_fails() -> None:
    fx = _fixture("test.ping")
    tampered = fx["body"].replace("Webhook configured successfully", "Webhook configured")
    with pytest.raises(WebhookSignatureError, match="Signature verification failed"):
        Webhook.verify(
            tampered,
            fx["headers"]["x-nope-signature"],
            fx["headers"]["x-nope-timestamp"],
            fx["secret"],
            max_age_seconds=0,
        )


def test_wrong_secret_fails() -> None:
    fx = _fixture("test.ping")
    with pytest.raises(WebhookSignatureError, match="Signature verification failed"):
        Webhook.verify(
            fx["body"],
            fx["headers"]["x-nope-signature"],
            fx["headers"]["x-nope-timestamp"],
            "whsec_" + "00" * 32,
            max_age_seconds=0,
        )


def test_stale_timestamp_fails_by_default() -> None:
    fx = _fixture("test.ping")
    assert int(time.time()) - int(fx["headers"]["x-nope-timestamp"]) > 300
    with pytest.raises(WebhookSignatureError, match="Timestamp too old"):
        Webhook.verify(
            fx["body"],
            fx["headers"]["x-nope-signature"],
            fx["headers"]["x-nope-timestamp"],
            fx["secret"],
        )


def test_future_timestamp_fails() -> None:
    secret = "whsec_" + "ab" * 32
    body = _fixture("test.ping")["body"]
    future = int(time.time()) + 3600
    signed = Webhook.sign(body, secret, timestamp=future)
    with pytest.raises(WebhookSignatureError, match="too far in future"):
        Webhook.verify(body, signed["signature"], signed["timestamp"], secret)


def test_max_age_zero_disables_freshness_check() -> None:
    fx = _fixture("test.ping")
    payload = Webhook.verify(
        fx["body"],
        fx["headers"]["x-nope-signature"],
        fx["headers"]["x-nope-timestamp"],
        fx["secret"],
        max_age_seconds=0,
    )
    assert payload.event == "test.ping"


def test_missing_headers() -> None:
    fx = _fixture("test.ping")
    with pytest.raises(WebhookSignatureError, match="Missing X-NOPE-Signature"):
        Webhook.verify(fx["body"], None, "1", fx["secret"])
    with pytest.raises(WebhookSignatureError, match="Missing X-NOPE-Timestamp"):
        Webhook.verify(fx["body"], "sha256=00", None, fx["secret"])
    with pytest.raises(WebhookSignatureError, match="Invalid timestamp"):
        Webhook.verify(fx["body"], "sha256=00", "soon", fx["secret"])
    with pytest.raises(WebhookSignatureError, match="secret is required"):
        Webhook.verify(fx["body"], "sha256=00", "1", "")
    with pytest.raises(WebhookSignatureError, match="Missing X-NOPE-Signature"):
        Webhook.verify_request(fx["body"], {}, fx["secret"])


def test_signature_without_prefix_is_accepted() -> None:
    fx = _fixture("test.ping")
    bare = fx["headers"]["x-nope-signature"][len("sha256=") :]
    payload = Webhook.verify(
        fx["body"], bare, fx["headers"]["x-nope-timestamp"], fx["secret"], max_age_seconds=0
    )
    assert payload.event == "test.ping"


def test_unknown_event_is_rejected_by_the_union() -> None:
    body = {
        "event": "risk.critical",
        "event_id": "evt_old",
        "timestamp": "2025-01-01T00:00:00Z",
        "api_version": "2025-01",
    }
    with pytest.raises(ValueError, match="event"):
        parse_webhook_payload(body)


def test_extra_fields_are_tolerated() -> None:
    body = dict(_fixture("test.ping")["payload"])
    body["future_field"] = {"nested": True}
    payload = parse_webhook_payload(body)
    assert isinstance(payload, TestPingPayload)
    assert payload.model_dump(mode="json", exclude_unset=True) == body


def test_payload_field_shapes() -> None:
    alert = parse_webhook_payload(_fixture("oversight.alert")["payload"])
    assert isinstance(alert, OversightAlertPayload)
    assert alert.concern == "high"
    assert alert.behaviors[0].category == "boundary_violations"
    assert alert.user_is_minor is False
    assert alert.conversation is None

    done = parse_webhook_payload(_fixture("oversight.ingestion.complete")["payload"])
    assert isinstance(done, OversightIngestionCompletePayload)
    assert done.concerns.high == 2
    assert done.top_behaviors[0].occurrence_count == 4
    assert done.processing_time_ms == 4321


def test_body_and_payload_agree_in_fixture() -> None:
    for event in EVENTS:
        fx = _fixture(event)
        assert json.loads(fx["body"]) == fx["payload"]
