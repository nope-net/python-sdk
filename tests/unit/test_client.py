"""Client construction and request plumbing, run against both client flavours."""

import pytest

from nope_net import (
    AsyncNopeClient,
    NopeAuthError,
    NopeClient,
    NopeRateLimitError,
    NopeServerError,
    NopeValidationError,
    __version__,
)
from tests.conftest import ClientFactory, FakeApi, load_fixture


class TestConstruction:
    def test_init_without_api_key(self) -> None:
        client = NopeClient(api_key=None)
        assert client.api_key is None
        client.close()

        client2 = NopeClient()
        assert client2.api_key is None
        client2.close()

    def test_init_with_defaults(self) -> None:
        with NopeClient(api_key="test_key") as client:
            assert client.base_url == "https://api.nope.net"
            assert client.timeout == 30.0

    def test_init_with_custom_options(self) -> None:
        with NopeClient(api_key="test_key", base_url="http://localhost:8788", timeout=60.0) as c:
            assert c.base_url == "http://localhost:8788"
            assert c.timeout == 60.0

    def test_base_url_trailing_slash_removed(self) -> None:
        with NopeClient(api_key="test_key", base_url="http://localhost:8788/") as client:
            assert client.base_url == "http://localhost:8788"

    def test_context_manager(self) -> None:
        with NopeClient(api_key="test_key") as client:
            assert client.api_key == "test_key"

    async def test_async_context_manager(self) -> None:
        async with AsyncNopeClient(api_key="test_key") as client:
            assert client.api_key == "test_key"


class TestRequestHeaders:
    async def test_user_agent_is_package_version(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/signpost/countries", json_body=load_fixture("signpost/countries.json"))
        client = make(api_key="test_key")
        await client.call("signpost_countries")
        await client.close()

        assert api.last_request.headers["user-agent"] == f"nope-python/{__version__}"
        assert __version__ == "4.0.1"

    async def test_bearer_auth_header(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/signpost/countries", json_body=load_fixture("signpost/countries.json"))
        client = make(api_key="nope_live_abc")
        await client.call("signpost_countries")
        await client.close()

        assert api.last_request.headers["authorization"] == "Bearer nope_live_abc"

    async def test_no_auth_header_without_key(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/signpost/countries", json_body=load_fixture("signpost/countries.json"))
        client = make()
        await client.call("signpost_countries")
        await client.close()

        assert "authorization" not in api.last_request.headers


class TestEvaluateGuards:
    async def test_requires_messages_or_text(self, make: ClientFactory) -> None:
        client = make(api_key="test_key")
        with pytest.raises(ValueError, match="Either 'messages' or 'text' must be provided"):
            await client.call("evaluate")
        await client.close()

    async def test_rejects_both_messages_and_text(self, make: ClientFactory) -> None:
        client = make(api_key="test_key")
        with pytest.raises(ValueError, match="Only one of"):
            await client.call(
                "evaluate", messages=[{"role": "user", "content": "test"}], text="test"
            )
        await client.close()


class TestEvaluateResponses:
    async def test_parses_v1_response(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/evaluate", json_body=load_fixture("evaluate/try.us.json"))
        client = make(api_key="test_key")
        result = await client.call(
            "evaluate", messages=[{"role": "user", "content": "I feel hopeless"}]
        )
        await client.close()

        assert result.request_id == "eval_1788396900000_fixture"
        assert result.speaker_severity == "moderate"
        assert result.speaker_imminence == "subacute"
        assert result.show_resources is True
        assert len(result.risks) == 1
        assert result.risks[0].subject == "self"
        assert result.risks[0].type == "suicide"
        assert api.last_request.url.path == "/v1/evaluate"

    async def test_text_input(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/evaluate", json_body=load_fixture("evaluate/auth.benign.json"))
        client = make(api_key="test_key")
        result = await client.call("evaluate", text="Patient is doing well today.")
        await client.close()

        assert result.speaker_severity == "none"
        assert result.show_resources is False
        assert api.json_of()["text"] == "Patient is doing well today."
        assert "messages" not in api.json_of()


class TestErrorMapping:
    async def test_auth_error(self, api: FakeApi, make: ClientFactory) -> None:
        api.add(
            "POST",
            "/v1/evaluate",
            status=401,
            json_body=load_fixture("errors/401.missing-auth.json"),
        )
        client = make(api_key="invalid_key")
        with pytest.raises(NopeAuthError) as exc_info:
            await client.call("evaluate", messages=[{"role": "user", "content": "test"}])
        await client.close()

        assert exc_info.value.status_code == 401
        assert "Missing or invalid Authorization header" in str(exc_info.value)

    async def test_validation_error(self, api: FakeApi, make: ClientFactory) -> None:
        api.add(
            "POST",
            "/v1/evaluate",
            status=400,
            json_body=load_fixture("errors/400.evaluate-role.json"),
        )
        client = make(api_key="test_key")
        with pytest.raises(NopeValidationError) as exc_info:
            await client.call("evaluate", messages=[{"role": "user", "content": "x"}])
        await client.close()

        assert exc_info.value.status_code == 400

    async def test_rate_limit_error(self, api: FakeApi, make: ClientFactory) -> None:
        api.add(
            "POST",
            "/v1/evaluate",
            status=429,
            headers={"Retry-After": "30"},
            json_body={"error": "rate_limit_exceeded"},
        )
        client = make(api_key="test_key", max_retries=0)
        with pytest.raises(NopeRateLimitError) as exc_info:
            await client.call("evaluate", messages=[{"role": "user", "content": "test"}])
        await client.close()

        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == 30.0

    async def test_server_error(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/evaluate", status=500, json_body={"error": "Internal server error"})
        client = make(api_key="test_key")
        with pytest.raises(NopeServerError) as exc_info:
            await client.call("evaluate", messages=[{"role": "user", "content": "test"}])
        await client.close()

        assert exc_info.value.status_code == 500


class TestSignpostSearch:
    async def test_requires_query(self, make: ClientFactory) -> None:
        client = make(api_key="test_key")
        with pytest.raises(ValueError, match="'query' is required"):
            await client.call("signpost_search", query="")
        await client.close()

    async def test_sends_query_params(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("GET", "/v1/signpost/search", json_body=load_fixture("signpost/search.auth.json"))
        client = make(api_key="test_key")
        result = await client.call(
            "signpost_search", query="lgbtq youth support", country="gb", limit=5, threshold=0.4
        )
        await client.close()

        params = dict(api.last_request.url.params)
        assert params == {
            "query": "lgbtq youth support",
            "country": "GB",
            "limit": "5",
            "threshold": "0.4",
        }
        assert result.count == 2
        assert result.results[0].similarity == pytest.approx(0.560408288549103)
        assert result.results[0].phone == "0345 3 30 30 30"
        assert result.timing is not None
        assert result.timing.total_ms == 150
