"""client.webhooks.* and client.billing.* namespaces on both clients."""

import pytest

from nope_net import (
    BillingBalanceResponse,
    BillingPricingResponse,
    BillingTopupResponse,
    BillingUsageHistoryResponse,
    BillingUsageResponse,
    NopeNotFoundError,
    NopeServerError,
    TestPingPayload,
    WebhookDeleteResponse,
    WebhookDeliveryResult,
    WebhookEventsResponse,
    WebhookListResponse,
    WebhookResponse,
    WebhookSecretResponse,
)
from tests.conftest import ClientFactory, FakeApi, load_fixture

WEBHOOK = {
    "id": "wh_1",
    "url": "https://example.com/hooks/nope",
    "min_risk_level": "high",
    "enabled": True,
    "include_conversation": False,
    "created_at": "2026-09-03T00:55:00.000Z",
    "updated_at": "2026-09-03T00:55:00.000Z",
}
WEBHOOK_WITH_SECRET = dict(WEBHOOK, secret="whsec_" + "ab" * 32)

EVENT = {
    "id": "wev_1",
    "webhook_id": "wh_1",
    "event_type": "test.ping",
    "payload": load_fixture("webhooks/test.ping.json")["payload"],
    "status": "sent",
    "http_status": 200,
    "attempt_count": 1,
    "last_attempt_at": "2026-09-03T00:55:01.000Z",
    "created_at": "2026-09-03T00:55:00.000Z",
}


class TestWebhooksNamespace:
    async def test_create(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/webhooks", status=201, json_body=WEBHOOK_WITH_SECRET)
        client = make(api_key="k")
        result = await client.call(
            "webhooks.create",
            "https://example.com/hooks/nope",
            min_risk_level="high",
            include_conversation=False,
        )
        await client.close()

        assert api.last_request.method == "POST"
        assert api.json_of() == {
            "url": "https://example.com/hooks/nope",
            "min_risk_level": "high",
            "include_conversation": False,
        }
        assert isinstance(result, WebhookResponse)
        assert result.secret == "whsec_" + "ab" * 32
        assert result.model_dump(mode="json", exclude_unset=True) == WEBHOOK_WITH_SECRET

    async def test_list(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/webhooks", json_body={"webhooks": [WEBHOOK]})
        client = make(api_key="k")
        result = await client.call("webhooks.list")
        await client.close()

        assert isinstance(result, WebhookListResponse)
        assert result.webhooks[0].id == "wh_1"
        assert result.webhooks[0].secret is None

    async def test_get(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/webhooks/wh_1", json_body=WEBHOOK)
        client = make(api_key="k")
        result = await client.call("webhooks.get", "wh_1")
        await client.close()

        assert result.url == "https://example.com/hooks/nope"

    async def test_update(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("PUT", "/v1/webhooks/wh_1", json_body=dict(WEBHOOK, enabled=False))
        client = make(api_key="k")
        result = await client.call(
            "webhooks.update", "wh_1", {"enabled": False, "min_risk_level": "critical"}
        )
        await client.close()

        assert api.last_request.method == "PUT"
        assert api.json_of() == {"enabled": False, "min_risk_level": "critical"}
        assert result.enabled is False

    async def test_delete(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("DELETE", "/v1/webhooks/wh_1", json_body={"success": True})
        client = make(api_key="k")
        result = await client.call("webhooks.delete", "wh_1")
        await client.close()

        assert api.last_request.method == "DELETE"
        assert isinstance(result, WebhookDeleteResponse)
        assert result.success is True

    async def test_regenerate_secret(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/webhooks/wh_1/regenerate-secret", json_body={"secret": "whsec_new"})
        client = make(api_key="k")
        result = await client.call("webhooks.regenerate_secret", "wh_1")
        await client.close()

        assert isinstance(result, WebhookSecretResponse)
        assert result.secret == "whsec_new"

    async def test_test_ping_success(self, api: FakeApi, make: ClientFactory) -> None:
        api.add(
            "POST",
            "/v1/webhooks/wh_1/test",
            json_body={"success": True, "http_status": 200, "duration_ms": 120},
        )
        client = make(api_key="k")
        result = await client.call("webhooks.test", "wh_1")
        await client.close()

        assert isinstance(result, WebhookDeliveryResult)
        assert result.success is True
        assert result.http_status == 200

    async def test_test_ping_failure_502_returns_result(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        body = {
            "success": False,
            "http_status": 500,
            "error_message": "HTTP 500",
            "duration_ms": 80,
        }
        api.add("POST", "/v1/webhooks/wh_1/test", status=502, json_body=body)
        client = make(api_key="k")
        result = await client.call("webhooks.test", "wh_1")
        await client.close()

        assert isinstance(result, WebhookDeliveryResult)
        assert result.success is False
        assert result.error_message == "HTTP 500"
        assert result.model_dump(mode="json", exclude_unset=True) == body

    async def test_test_ping_gateway_502_still_raises(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        api.add("POST", "/v1/webhooks/wh_1/test", status=502, text="Bad Gateway")
        client = make(api_key="k")
        with pytest.raises(NopeServerError):
            await client.call("webhooks.test", "wh_1")
        await client.close()

    async def test_test_ping_404(self, api: FakeApi, make: ClientFactory) -> None:
        api.add(
            "POST", "/v1/webhooks/wh_x/test", status=404, json_body={"error": "Webhook not found"}
        )
        client = make(api_key="k")
        with pytest.raises(NopeNotFoundError):
            await client.call("webhooks.test", "wh_x")
        await client.close()

    async def test_events_for_one_webhook(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/webhooks/wh_1/events", json_body={"events": [EVENT]})
        client = make(api_key="k")
        result = await client.call("webhooks.events", "wh_1", limit=10)
        await client.close()

        assert dict(api.last_request.url.params) == {"limit": "10"}
        assert isinstance(result, WebhookEventsResponse)
        event = result.events[0]
        assert event.status == "sent"
        assert isinstance(event.payload, TestPingPayload)
        assert result.model_dump(mode="json", exclude_unset=True) == {"events": [EVENT]}

    async def test_events_for_all_webhooks(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/webhooks/events", json_body={"events": []})
        client = make(api_key="k")
        result = await client.call("webhooks.events")
        await client.close()

        assert api.last_request.url.path == "/v1/webhooks/events"
        assert dict(api.last_request.url.params) == {}
        assert result.events == []

    async def test_legacy_event_payload_is_kept_as_dict(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        legacy = dict(EVENT, event_type="risk.critical", payload={"event": "risk.critical"})
        api.add("GET", "/v1/webhooks/events", json_body={"events": [legacy]})
        client = make(api_key="k")
        result = await client.call("webhooks.events")
        await client.close()

        assert result.events[0].payload == {"event": "risk.critical"}
        assert result.events[0].event_type == "risk.critical"

    @pytest.mark.parametrize(
        ("method", "args"),
        [
            ("webhooks.create", ("https://example.com",)),
            ("webhooks.list", ()),
            ("webhooks.get", ("wh_1",)),
            ("webhooks.update", ("wh_1", {})),
            ("webhooks.delete", ("wh_1",)),
            ("webhooks.regenerate_secret", ("wh_1",)),
            ("webhooks.test", ("wh_1",)),
            ("webhooks.events", ()),
            ("billing.balance", ()),
            ("billing.usage", ()),
            ("billing.usage_history", ()),
            ("billing.topup", (10000,)),
        ],
    )
    async def test_not_available_in_demo(
        self, make: ClientFactory, method: str, args: tuple
    ) -> None:
        client = make(demo=True)
        with pytest.raises(ValueError, match="not available in demo mode"):
            await client.call(method, *args)
        await client.close()


class TestBillingNamespace:
    async def test_balance(self, api: FakeApi, make: ClientFactory) -> None:
        body = load_fixture("billing/balance.json")
        api.add("GET", "/v1/billing/balance", json_body=body)
        client = make(api_key="k")
        result = await client.call("billing.balance")
        await client.close()

        assert isinstance(result, BillingBalanceResponse)
        assert result.balance_mills == 12345.6
        assert result.balance_formatted == "$12.35"
        assert result.estimated_evaluates == 4115
        assert result.estimated_screens == 12345
        assert result.low_balance is False
        assert result.topup_options[0].amount_mills == 10000
        assert result.topup_options[0].screens == 10000

    async def test_usage_with_dates(self, api: FakeApi, make: ClientFactory) -> None:
        body = load_fixture("billing/usage.json")
        api.add("GET", "/v1/billing/usage", json_body=body)
        client = make(api_key="k")
        result = await client.call(
            "billing.usage", start_date="2026-09-01", end_date="2026-09-03T00:55:00Z"
        )
        await client.close()

        assert dict(api.last_request.url.params) == {
            "start_date": "2026-09-01",
            "end_date": "2026-09-03T00:55:00Z",
        }
        assert isinstance(result, BillingUsageResponse)
        assert result.total_spend_mills == 123
        assert result.breakdown[0].endpoint == "oversight_analyze"
        assert result.breakdown[0].referrals == 0

    async def test_usage_defaults_send_no_params(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/billing/usage", json_body=load_fixture("billing/usage.json"))
        client = make(api_key="k")
        await client.call("billing.usage")
        await client.close()

        assert dict(api.last_request.url.params) == {}

    async def test_usage_history(self, api: FakeApi, make: ClientFactory) -> None:
        body = {
            "records": [
                {
                    "id": "use_1",
                    "endpoint": "evaluate",
                    "cost_mills": 3,
                    "cost_formatted": "$0.003",
                    "metadata": {"speaker_severity": "none"},
                    "created_at": "2026-09-03T00:55:00.000Z",
                }
            ],
            "total": 1,
            "limit": 20,
            "offset": 0,
        }
        api.add("GET", "/v1/billing/usage/history", json_body=body)
        client = make(api_key="k")
        result = await client.call(
            "billing.usage_history",
            limit=20,
            offset=0,
            endpoint="evaluate",
            start_date="2026-09-01",
        )
        await client.close()

        assert dict(api.last_request.url.params) == {
            "limit": "20",
            "offset": "0",
            "endpoint": "evaluate",
            "start_date": "2026-09-01",
        }
        assert isinstance(result, BillingUsageHistoryResponse)
        assert result.records[0].metadata == {"speaker_severity": "none"}
        assert result.model_dump(mode="json", exclude_unset=True) == body

    async def test_pricing_in_demo_mode(self, api: FakeApi, make: ClientFactory) -> None:
        """The price list is public, so a demo client reads it like any other."""
        body = load_fixture("billing/pricing.json")
        api.add("GET", "/v1/billing/pricing", json_body=body)
        client = make(demo=True)
        result = await client.call("billing.pricing")
        await client.close()

        assert api.last_request.url.path == "/v1/billing/pricing"
        assert "authorization" not in api.last_request.headers
        assert isinstance(result, BillingPricingResponse)

    async def test_pricing_without_key(self, api: FakeApi, make: ClientFactory) -> None:
        body = load_fixture("billing/pricing.json")
        api.add("GET", "/v1/billing/pricing", json_body=body)
        client = make()
        result = await client.call("billing.pricing")
        await client.close()

        assert "authorization" not in api.last_request.headers
        assert isinstance(result, BillingPricingResponse)
        assert result.unit == "mills"
        assert result.pricing["evaluate"].cost_mills == 3
        assert result.pricing["screen"].cost_mills == 1
        assert result.pricing["oversight_ingest"].cost_display == "$0.10"
        assert "resources" not in result.pricing
        assert result.free_credit_mills == 1000

    async def test_topup(self, api: FakeApi, make: ClientFactory) -> None:
        api.add(
            "POST",
            "/v1/billing/topup",
            json_body={"checkout_url": "https://checkout.stripe.com/c/pay/cs_test"},
        )
        client = make(api_key="k")
        result = await client.call(
            "billing.topup", 25000, success_url="https://example.com/ok", cancel_url=None
        )
        await client.close()

        assert api.json_of() == {"amount_mills": 25000, "success_url": "https://example.com/ok"}
        assert isinstance(result, BillingTopupResponse)
        assert result.checkout_url.startswith("https://checkout.stripe.com/")
