"""Namespace objects for the webhook-management and billing routes.

``client.webhooks`` and ``client.billing`` are small objects bound to a client;
they build requests here and send them through the client's shared ``_request``
so retries, error mapping and ``last_response_meta`` behave the same as every
other call. ``billing.pricing`` is public and works in demo mode; nothing else
here has a demo route.
"""

import json
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from ._requests import JsonDict, dump, invalid_request, not_available_in_demo
from .errors import NopeServerError
from .types import (
    BillingBalanceResponse,
    BillingPricingResponse,
    BillingTopupResponse,
    BillingUsageHistoryResponse,
    BillingUsageResponse,
)
from .webhook import (
    WebhookDeleteResponse,
    WebhookDeliveryResult,
    WebhookEventsResponse,
    WebhookListResponse,
    WebhookResponse,
    WebhookRiskLevel,
    WebhookSecretResponse,
    WebhookUpdate,
)

if TYPE_CHECKING:
    from .client import AsyncNopeClient, NopeClient


# =============================================================================
# Shared builders
# =============================================================================


def _demo_guard(demo: bool, name: str) -> None:
    if demo:
        raise not_available_in_demo(f"{name}() is not available in demo mode. Use an API key.")


def build_webhook_create_body(
    url: str,
    min_risk_level: Optional[WebhookRiskLevel],
    include_conversation: Optional[bool],
) -> JsonDict:
    if not url:
        raise invalid_request("'url' is required")
    body: JsonDict = {"url": url}
    if min_risk_level is not None:
        body["min_risk_level"] = min_risk_level
    if include_conversation is not None:
        body["include_conversation"] = include_conversation
    return body


def build_webhook_update_body(patch: Union[WebhookUpdate, JsonDict]) -> JsonDict:
    return dump(patch)


def webhook_events_path(webhook_id: Optional[str]) -> str:
    return f"/v1/webhooks/{webhook_id}/events" if webhook_id else "/v1/webhooks/events"


def limit_params(limit: Optional[int]) -> Dict[str, str]:
    return {"limit": str(limit)} if limit is not None else {}


def delivery_result_from_error(err: NopeServerError) -> Optional[WebhookDeliveryResult]:
    """The test-ping route answers 502 with a WebhookDeliveryResult body on delivery failure."""
    if err.status_code != 502 or not err.response_body:
        return None
    try:
        body = json.loads(err.response_body)
    except ValueError:
        return None
    if not isinstance(body, dict) or "success" not in body or "error" in body:
        return None
    return WebhookDeliveryResult.model_validate(body)


def build_usage_params(start_date: Optional[str], end_date: Optional[str]) -> Dict[str, str]:
    params: Dict[str, str] = {}
    if start_date is not None:
        params["start_date"] = start_date
    if end_date is not None:
        params["end_date"] = end_date
    return params


def build_usage_history_params(
    limit: Optional[int],
    offset: Optional[int],
    endpoint: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
) -> Dict[str, str]:
    params: Dict[str, str] = {}
    if limit is not None:
        params["limit"] = str(limit)
    if offset is not None:
        params["offset"] = str(offset)
    if endpoint is not None:
        params["endpoint"] = endpoint
    params.update(build_usage_params(start_date, end_date))
    return params


def build_topup_body(
    amount_mills: int, success_url: Optional[str], cancel_url: Optional[str]
) -> JsonDict:
    body: JsonDict = {"amount_mills": amount_mills}
    if success_url is not None:
        body["success_url"] = success_url
    if cancel_url is not None:
        body["cancel_url"] = cancel_url
    return body


# =============================================================================
# Webhooks
# =============================================================================


class WebhooksClient:
    """``client.webhooks``: manage webhook endpoints (``/v1/webhooks``).

    Requires a paid plan for ``create`` (403 ``paid_plan_required`` otherwise).
    The family is rate-limited at 30 requests per minute.
    """

    def __init__(self, client: "NopeClient") -> None:
        self._client = client

    def create(
        self,
        url: str,
        *,
        min_risk_level: Optional[WebhookRiskLevel] = None,
        include_conversation: Optional[bool] = None,
    ) -> WebhookResponse:
        """Register an HTTPS endpoint. The response carries ``secret`` once; store it."""
        _demo_guard(self._client.demo, "webhooks.create")
        body = build_webhook_create_body(url, min_risk_level, include_conversation)
        return WebhookResponse.model_validate(
            self._client._request("POST", "/v1/webhooks", json=body)
        )

    def list(self) -> WebhookListResponse:
        """All webhooks on the account (without secrets)."""
        _demo_guard(self._client.demo, "webhooks.list")
        return WebhookListResponse.model_validate(self._client._request("GET", "/v1/webhooks"))

    def get(self, webhook_id: str) -> WebhookResponse:
        """One webhook by id (404 raises ``NopeNotFoundError``)."""
        _demo_guard(self._client.demo, "webhooks.get")
        return WebhookResponse.model_validate(
            self._client._request("GET", f"/v1/webhooks/{webhook_id}")
        )

    def update(
        self, webhook_id: str, patch: Union[WebhookUpdate, Dict[str, Any]]
    ) -> WebhookResponse:
        """Change ``url``, ``min_risk_level``, ``enabled`` or ``include_conversation``."""
        _demo_guard(self._client.demo, "webhooks.update")
        return WebhookResponse.model_validate(
            self._client._request(
                "PUT", f"/v1/webhooks/{webhook_id}", json=build_webhook_update_body(patch)
            )
        )

    def delete(self, webhook_id: str) -> WebhookDeleteResponse:
        """Delete a webhook."""
        _demo_guard(self._client.demo, "webhooks.delete")
        return WebhookDeleteResponse.model_validate(
            self._client._request("DELETE", f"/v1/webhooks/{webhook_id}")
        )

    def regenerate_secret(self, webhook_id: str) -> WebhookSecretResponse:
        """Rotate the signing secret; the old one stops verifying at once."""
        _demo_guard(self._client.demo, "webhooks.regenerate_secret")
        return WebhookSecretResponse.model_validate(
            self._client._request("POST", f"/v1/webhooks/{webhook_id}/regenerate-secret")
        )

    def test(self, webhook_id: str) -> WebhookDeliveryResult:
        """Send a ``test.ping``. A failed delivery returns ``success=False`` rather than raising."""
        _demo_guard(self._client.demo, "webhooks.test")
        try:
            data = self._client._request("POST", f"/v1/webhooks/{webhook_id}/test")
        except NopeServerError as err:
            result = delivery_result_from_error(err)
            if result is None:
                raise
            return result
        return WebhookDeliveryResult.model_validate(data)

    def events(
        self, webhook_id: Optional[str] = None, *, limit: Optional[int] = None
    ) -> WebhookEventsResponse:
        """Recent deliveries for one webhook, or for the whole account (``limit`` up to 100)."""
        _demo_guard(self._client.demo, "webhooks.events")
        return WebhookEventsResponse.model_validate(
            self._client._request(
                "GET", webhook_events_path(webhook_id), params=limit_params(limit)
            )
        )


class AsyncWebhooksClient:
    """Async twin of :class:`WebhooksClient`."""

    def __init__(self, client: "AsyncNopeClient") -> None:
        self._client = client

    async def create(
        self,
        url: str,
        *,
        min_risk_level: Optional[WebhookRiskLevel] = None,
        include_conversation: Optional[bool] = None,
    ) -> WebhookResponse:
        _demo_guard(self._client.demo, "webhooks.create")
        body = build_webhook_create_body(url, min_risk_level, include_conversation)
        return WebhookResponse.model_validate(
            await self._client._request("POST", "/v1/webhooks", json=body)
        )

    async def list(self) -> WebhookListResponse:
        _demo_guard(self._client.demo, "webhooks.list")
        return WebhookListResponse.model_validate(
            await self._client._request("GET", "/v1/webhooks")
        )

    async def get(self, webhook_id: str) -> WebhookResponse:
        _demo_guard(self._client.demo, "webhooks.get")
        return WebhookResponse.model_validate(
            await self._client._request("GET", f"/v1/webhooks/{webhook_id}")
        )

    async def update(
        self, webhook_id: str, patch: Union[WebhookUpdate, Dict[str, Any]]
    ) -> WebhookResponse:
        _demo_guard(self._client.demo, "webhooks.update")
        return WebhookResponse.model_validate(
            await self._client._request(
                "PUT", f"/v1/webhooks/{webhook_id}", json=build_webhook_update_body(patch)
            )
        )

    async def delete(self, webhook_id: str) -> WebhookDeleteResponse:
        _demo_guard(self._client.demo, "webhooks.delete")
        return WebhookDeleteResponse.model_validate(
            await self._client._request("DELETE", f"/v1/webhooks/{webhook_id}")
        )

    async def regenerate_secret(self, webhook_id: str) -> WebhookSecretResponse:
        _demo_guard(self._client.demo, "webhooks.regenerate_secret")
        return WebhookSecretResponse.model_validate(
            await self._client._request("POST", f"/v1/webhooks/{webhook_id}/regenerate-secret")
        )

    async def test(self, webhook_id: str) -> WebhookDeliveryResult:
        _demo_guard(self._client.demo, "webhooks.test")
        try:
            data = await self._client._request("POST", f"/v1/webhooks/{webhook_id}/test")
        except NopeServerError as err:
            result = delivery_result_from_error(err)
            if result is None:
                raise
            return result
        return WebhookDeliveryResult.model_validate(data)

    async def events(
        self, webhook_id: Optional[str] = None, *, limit: Optional[int] = None
    ) -> WebhookEventsResponse:
        _demo_guard(self._client.demo, "webhooks.events")
        return WebhookEventsResponse.model_validate(
            await self._client._request(
                "GET", webhook_events_path(webhook_id), params=limit_params(limit)
            )
        )


# =============================================================================
# Billing
# =============================================================================


class BillingClient:
    """``client.billing``: balance, usage and pricing (``/v1/billing/*``).

    Amounts are in mills (1 mill = $0.001). ``pricing()`` is public;
    the other routes validate the API key in-route.
    """

    def __init__(self, client: "NopeClient") -> None:
        self._client = client

    def balance(self) -> BillingBalanceResponse:
        """Current balance, low-balance flag, recent top-ups and top-up options."""
        _demo_guard(self._client.demo, "billing.balance")
        return BillingBalanceResponse.model_validate(
            self._client._request("GET", "/v1/billing/balance")
        )

    def usage(
        self, *, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> BillingUsageResponse:
        """Spend by endpoint for a period (defaults to the current month). Dates are ISO strings."""
        _demo_guard(self._client.demo, "billing.usage")
        return BillingUsageResponse.model_validate(
            self._client._request(
                "GET", "/v1/billing/usage", params=build_usage_params(start_date, end_date)
            )
        )

    def usage_history(
        self,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        endpoint: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> BillingUsageHistoryResponse:
        """Paginated per-call usage records (``limit`` up to 100, default 50)."""
        _demo_guard(self._client.demo, "billing.usage_history")
        params = build_usage_history_params(limit, offset, endpoint, start_date, end_date)
        return BillingUsageHistoryResponse.model_validate(
            self._client._request("GET", "/v1/billing/usage/history", params=params)
        )

    def pricing(self) -> BillingPricingResponse:
        """Current per-endpoint pricing and top-up options (public; works in demo mode)."""
        return BillingPricingResponse.model_validate(
            self._client._request("GET", "/v1/billing/pricing")
        )

    def topup(
        self,
        amount_mills: int,
        *,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> BillingTopupResponse:
        """Create a Stripe Checkout session; ``amount_mills`` must be one of the top-up options."""
        _demo_guard(self._client.demo, "billing.topup")
        return BillingTopupResponse.model_validate(
            self._client._request(
                "POST",
                "/v1/billing/topup",
                json=build_topup_body(amount_mills, success_url, cancel_url),
            )
        )


class AsyncBillingClient:
    """Async twin of :class:`BillingClient`."""

    def __init__(self, client: "AsyncNopeClient") -> None:
        self._client = client

    async def balance(self) -> BillingBalanceResponse:
        _demo_guard(self._client.demo, "billing.balance")
        return BillingBalanceResponse.model_validate(
            await self._client._request("GET", "/v1/billing/balance")
        )

    async def usage(
        self, *, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> BillingUsageResponse:
        _demo_guard(self._client.demo, "billing.usage")
        return BillingUsageResponse.model_validate(
            await self._client._request(
                "GET", "/v1/billing/usage", params=build_usage_params(start_date, end_date)
            )
        )

    async def usage_history(
        self,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        endpoint: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> BillingUsageHistoryResponse:
        _demo_guard(self._client.demo, "billing.usage_history")
        params = build_usage_history_params(limit, offset, endpoint, start_date, end_date)
        return BillingUsageHistoryResponse.model_validate(
            await self._client._request("GET", "/v1/billing/usage/history", params=params)
        )

    async def pricing(self) -> BillingPricingResponse:
        """Current per-endpoint pricing and top-up options (public; works in demo mode)."""
        return BillingPricingResponse.model_validate(
            await self._client._request("GET", "/v1/billing/pricing")
        )

    async def topup(
        self,
        amount_mills: int,
        *,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
    ) -> BillingTopupResponse:
        _demo_guard(self._client.demo, "billing.topup")
        return BillingTopupResponse.model_validate(
            await self._client._request(
                "POST",
                "/v1/billing/topup",
                json=build_topup_body(amount_mills, success_url, cancel_url),
            )
        )
