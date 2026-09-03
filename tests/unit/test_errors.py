"""Error mapping: status code and body -> exception class, code, message, extras.

Bodies for 402/403/410/429/503 are source-derived (tests/unit/fixtures_derived/);
400/401/404/413 come from the live captures under tests/fixtures/errors/.
Every case runs against both NopeClient and AsyncNopeClient.
"""

import httpx
import pytest

from nope_net import (
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
from tests.conftest import ClientFactory, FakeApi, load_derived, load_fixture

MESSAGES = [{"role": "user", "content": "hello"}]


async def _evaluate(client: object, **kwargs: object) -> object:
    return await client.call("evaluate", messages=MESSAGES, **kwargs)  # type: ignore[attr-defined]


class TestInsufficientBalance:
    async def test_402_evaluate_body(self, api: FakeApi, make: ClientFactory) -> None:
        body, headers = load_derived("402.evaluate.json")
        api.add("POST", "/v1/evaluate", status=402, json_body=body, headers=headers)
        client = make(api_key="k")
        with pytest.raises(NopeInsufficientBalanceError) as exc_info:
            await _evaluate(client)
        await client.close()

        err = exc_info.value
        assert err.status_code == 402
        assert err.code == "insufficient_balance"
        assert err.message == body["message"]
        assert err.balance_mills == 0
        assert err.required_mills == 3
        assert err.formatted_current == "$0"
        assert err.formatted_required == "$0.003"
        assert err.topup_url == "https://dashboard.nope.net/billing"
        assert err.per_conversation_mills is None
        assert err.conversations is None
        assert body["message"] in str(err)
        assert isinstance(err, NopeError)

    async def test_402_ingest_body(self, api: FakeApi, make: ClientFactory) -> None:
        body, _ = load_derived("402.ingest.json")
        api.add("POST", "/v1/oversight/ingest", status=402, json_body=body)
        client = make(api_key="k")
        with pytest.raises(NopeInsufficientBalanceError) as exc_info:
            await client.call(
                "oversight_ingest",
                conversations=[{"conversation_id": "c1", "messages": MESSAGES}],
            )
        await client.close()

        err = exc_info.value
        assert err.required_mills == 200
        assert err.per_conversation_mills == 100
        assert err.conversations == 2


class TestRateLimit:
    async def test_429_code_message_and_fields(self, api: FakeApi, make: ClientFactory) -> None:
        body, headers = load_derived("429.rate-limit.json")
        api.add("POST", "/v1/evaluate", status=429, json_body=body, headers=headers)
        client = make(api_key="k", max_retries=0)
        with pytest.raises(NopeRateLimitError) as exc_info:
            await _evaluate(client)
        await client.close()

        err = exc_info.value
        assert err.status_code == 429
        assert err.code == "rate_limit_exceeded"
        assert err.message == "Rate limit exceeded. Please retry after 7 seconds."
        assert err.retry_after == 7.0
        assert err.limit == 10
        assert err.remaining == 0
        assert err.reset == 1788396967000

    async def test_429_retry_after_body_fallback(self, api: FakeApi, make: ClientFactory) -> None:
        body, _ = load_derived("429.rate-limit.json")
        api.add("POST", "/v1/evaluate", status=429, json_body=body)
        client = make(api_key="k", max_retries=0)
        with pytest.raises(NopeRateLimitError) as exc_info:
            await _evaluate(client)
        await client.close()

        assert exc_info.value.retry_after == 7.0

    async def test_429_header_wins_over_body(self, api: FakeApi, make: ClientFactory) -> None:
        body, _ = load_derived("429.rate-limit.json")
        api.add("POST", "/v1/evaluate", status=429, json_body=body, headers={"Retry-After": "12"})
        client = make(api_key="k", max_retries=0)
        with pytest.raises(NopeRateLimitError) as exc_info:
            await _evaluate(client)
        await client.close()

        assert exc_info.value.retry_after == 12.0

    async def test_429_without_hints(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/evaluate", status=429, json_body={"error": "rate_limit_exceeded"})
        client = make(api_key="k", max_retries=0)
        with pytest.raises(NopeRateLimitError) as exc_info:
            await _evaluate(client)
        await client.close()

        assert exc_info.value.retry_after is None
        assert exc_info.value.limit is None


class TestServerErrors:
    async def test_503_service_unavailable(self, api: FakeApi, make: ClientFactory) -> None:
        body, headers = load_derived("503.service-unavailable.json")
        api.add("POST", "/v1/evaluate", status=503, json_body=body, headers=headers)
        client = make(api_key="k", max_retries=0)
        with pytest.raises(NopeServiceUnavailableError) as exc_info:
            await _evaluate(client)
        await client.close()

        err = exc_info.value
        assert isinstance(err, NopeServerError)
        assert err.status_code == 503
        assert err.code == "service_unavailable"
        assert err.retry_after == 5.0
        assert err.message == body["message"]

    async def test_503_dependency_unavailable(self, api: FakeApi, make: ClientFactory) -> None:
        body, headers = load_derived("503.dependency-unavailable.json")
        api.add("POST", "/v1/evaluate", status=503, json_body=body, headers=headers)
        client = make(api_key="k", max_retries=0)
        with pytest.raises(NopeServiceUnavailableError) as exc_info:
            await _evaluate(client)
        await client.close()

        assert exc_info.value.code == "auth_unavailable"

    async def test_503_body_retry_after_fallback(self, api: FakeApi, make: ClientFactory) -> None:
        body, _ = load_derived("503.service-unavailable.json")
        api.add("POST", "/v1/evaluate", status=503, json_body=body)
        client = make(api_key="k", max_retries=0)
        with pytest.raises(NopeServiceUnavailableError) as exc_info:
            await _evaluate(client)
        await client.close()

        assert exc_info.value.retry_after == 5.0

    async def test_500_generic(self, api: FakeApi, make: ClientFactory) -> None:
        api.add(
            "POST",
            "/v1/evaluate",
            status=500,
            json_body={"error": "Internal server error", "message": "boom"},
        )
        client = make(api_key="k")
        with pytest.raises(NopeServerError) as exc_info:
            await _evaluate(client)
        await client.close()

        err = exc_info.value
        assert type(err) is NopeServerError
        assert err.status_code == 500
        assert err.code is None
        assert err.message == "boom"
        assert err.retry_after is None

    async def test_non_json_body_uses_status_text(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/evaluate", status=502, text="<html>Bad Gateway</html>")
        client = make(api_key="k")
        with pytest.raises(NopeServerError) as exc_info:
            await _evaluate(client)
        await client.close()

        err = exc_info.value
        assert err.status_code == 502
        assert err.message == "Bad Gateway"
        assert err.response_body == "<html>Bad Gateway</html>"
        assert err.code is None


class TestClientErrors:
    async def test_413_maps_to_validation_error(self, api: FakeApi, make: ClientFactory) -> None:
        body = load_fixture("errors/413.payload-too-large.json")
        api.add("POST", "/v1/evaluate", status=413, json_body=body)
        client = make(api_key="k")
        with pytest.raises(NopeValidationError) as exc_info:
            await _evaluate(client)
        await client.close()

        err = exc_info.value
        assert err.status_code == 413
        assert err.message == "Payload too large"
        assert err.details == {"max_bytes": 524288}
        assert err.code is None

    async def test_400_details_carry_extras(self, api: FakeApi, make: ClientFactory) -> None:
        body = load_fixture("errors/400.signpost-scope.json")
        api.add("GET", "/v1/signpost", status=400, json_body=body)
        client = make(api_key="k")
        with pytest.raises(NopeValidationError) as exc_info:
            await client.call("signpost", country="US")
        await client.close()

        err = exc_info.value
        assert err.details["invalid_scopes"] == ["suicide_prevention"]
        assert err.details["hint"] == "See docs.nope.net for valid scope values"
        assert "error" not in err.details

    async def test_400_oversight_code_and_details(self, api: FakeApi, make: ClientFactory) -> None:
        api.add(
            "POST",
            "/v1/oversight/analyze",
            status=400,
            json_body={
                "error": "Conversation too long",
                "code": "conversation_too_long",
                "details": {"max_messages": 500},
            },
        )
        client = make(api_key="k")
        with pytest.raises(NopeValidationError) as exc_info:
            await client.call("oversight_analyze", conversation={"messages": MESSAGES})
        await client.close()

        err = exc_info.value
        assert err.code == "conversation_too_long"
        assert err.message == "Conversation too long"
        assert err.details["details"] == {"max_messages": 500}

    async def test_401(self, api: FakeApi, make: ClientFactory) -> None:
        body = load_fixture("errors/401.missing-auth.json")
        api.add("POST", "/v1/evaluate", status=401, json_body=body)
        client = make()
        with pytest.raises(NopeAuthError) as exc_info:
            await _evaluate(client)
        await client.close()

        assert exc_info.value.message == body["error"]
        assert exc_info.value.code is None

    async def test_403_feature(self, api: FakeApi, make: ClientFactory) -> None:
        body, _ = load_derived("403.feature.json")
        api.add("POST", "/v1/oversight/analyze", status=403, json_body=body)
        client = make(api_key="k")
        with pytest.raises(NopeFeatureError) as exc_info:
            await client.call("oversight_analyze", conversation={"messages": MESSAGES})
        await client.close()

        err = exc_info.value
        assert err.feature == "OVERSIGHT"
        assert err.required_access == "admin"
        assert err.upgrade_url is None

    async def test_403_upgrade_url_demo(self, api: FakeApi, make: ClientFactory) -> None:
        body, _ = load_derived("403.upgrade-url.json")
        api.add("POST", "/v1/try/evaluate", status=403, json_body=body)
        client = make(demo=True)
        with pytest.raises(NopeFeatureError) as exc_info:
            await _evaluate(client)
        await client.close()

        err = exc_info.value
        assert err.feature == "paid_plan"
        assert err.upgrade_url == "https://dashboard.nope.net"
        assert err.message == body["error"]

    async def test_403_paid_plan_required(self, api: FakeApi, make: ClientFactory) -> None:
        body, _ = load_derived("403.paid-plan.json")
        api.add("POST", "/v1/evaluate", status=403, json_body=body)
        client = make(api_key="k")
        with pytest.raises(NopeFeatureError) as exc_info:
            await _evaluate(client)
        await client.close()

        err = exc_info.value
        assert err.code == "paid_plan_required"
        assert err.feature == "paid_plan"
        assert err.upgrade_url == "https://dashboard.nope.net/billing"
        assert err.message == body["message"]

    async def test_403_plain(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/evaluate", status=403, json_body={"error": "Admin access required"})
        client = make(api_key="k")
        with pytest.raises(NopeError) as exc_info:
            await _evaluate(client)
        await client.close()

        assert type(exc_info.value) is NopeError
        assert exc_info.value.status_code == 403

    async def test_404(self, api: FakeApi, make: ClientFactory) -> None:
        body = load_fixture("errors/404.signpost-id.json")
        api.add(
            "GET", "/v1/signpost/00000000-0000-4000-8000-000000000000", status=404, json_body=body
        )
        client = make()
        with pytest.raises(NopeNotFoundError) as exc_info:
            await client.call("signpost_by_id", "00000000-0000-4000-8000-000000000000")
        await client.close()

        assert exc_info.value.status_code == 404
        assert exc_info.value.message == "Resource not found"

    async def test_410(self, api: FakeApi, make: ClientFactory) -> None:
        body, _ = load_derived("410.gone.json")
        api.add("POST", "/v1/evaluate", status=410, json_body=body)
        client = make(api_key="k")
        with pytest.raises(NopeError) as exc_info:
            await _evaluate(client)
        await client.close()

        err = exc_info.value
        assert type(err) is NopeError
        assert err.status_code == 410
        assert err.code == "gone"
        assert err.message == body["message"]


class TestConnectionErrors:
    async def test_connect_error(self, client_kind: str) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        from tests.conftest import ClientRunner, FakeApi

        fake = FakeApi()
        fake.handle = boom  # type: ignore[method-assign]
        from tests.conftest import make_client

        client: ClientRunner = make_client(client_kind, fake, api_key="k")
        with pytest.raises(NopeConnectionError) as exc_info:
            await _evaluate(client)
        await client.close()

        assert "Failed to connect" in str(exc_info.value)
        assert isinstance(exc_info.value.original_error, httpx.ConnectError)

    async def test_timeout_error(self, client_kind: str) -> None:
        def slow(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        from tests.conftest import FakeApi, make_client

        fake = FakeApi()
        fake.handle = slow  # type: ignore[method-assign]
        client = make_client(client_kind, fake, api_key="k", timeout=1.5)
        with pytest.raises(NopeConnectionError) as exc_info:
            await _evaluate(client)
        await client.close()

        assert "timed out after 1.5s" in str(exc_info.value)


def test_no_nope_test_key_claims_in_source() -> None:
    """The API has no nope_test_ key class; the SDK must not promise one."""
    import pathlib

    import nope_net

    src_dir = pathlib.Path(nope_net.__file__).parent
    offenders = [
        path.name for path in src_dir.rglob("*.py") if "nope_test_" in path.read_text("utf-8")
    ]
    assert offenders == []
