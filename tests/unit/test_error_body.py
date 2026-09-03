"""Every ``NopeError`` carries ``body`` (the parsed JSON object) and ``details``.

``response_body`` stays the raw text. ``body`` is the decoded object when the
response was a JSON object and ``None`` otherwise (HTML from a proxy, a bare
JSON string, a transport failure). ``details`` is ``{}`` on every class; only
``NopeValidationError`` fills it. Fixtures: the live 401 and 413 captures plus
the source-derived 402. Both client flavours run every row.
"""

import json

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
from tests.conftest import ClientFactory, FakeApi, load_derived, load_fixture, make_client

MESSAGES = [{"role": "user", "content": "hello"}]
ERROR_CLASSES = [
    NopeError,
    NopeAuthError,
    NopeValidationError,
    NopeInsufficientBalanceError,
    NopeFeatureError,
    NopeNotFoundError,
    NopeRateLimitError,
    NopeServerError,
    NopeServiceUnavailableError,
    NopeConnectionError,
]


class TestParsedBody:
    async def test_401_body_is_the_parsed_object(self, api: FakeApi, make: ClientFactory) -> None:
        body = load_fixture("errors/401.missing-auth.json")
        api.add("POST", "/v1/evaluate", status=401, json_body=body)
        client = make()
        with pytest.raises(NopeAuthError) as exc_info:
            await client.call("evaluate", messages=MESSAGES)
        await client.close()

        err = exc_info.value
        assert err.body == {"error": "Missing or invalid Authorization header"}
        assert isinstance(err.response_body, str)
        assert json.loads(err.response_body) == body
        assert err.details == {}

    async def test_413_body_and_details(self, api: FakeApi, make: ClientFactory) -> None:
        body = load_fixture("errors/413.payload-too-large.json")
        api.add("POST", "/v1/evaluate", status=413, json_body=body)
        client = make(api_key="k")
        with pytest.raises(NopeValidationError) as exc_info:
            await client.call("evaluate", messages=MESSAGES)
        await client.close()

        err = exc_info.value
        assert err.body == {"error": "Payload too large", "max_bytes": 524288}
        assert err.details == {"max_bytes": 524288}
        assert err.body is not err.details
        assert json.loads(err.response_body or "") == body

    async def test_402_body_keeps_the_nested_balance(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        body, headers = load_derived("402.evaluate.json")
        api.add("POST", "/v1/evaluate", status=402, json_body=body, headers=headers)
        client = make(api_key="k")
        with pytest.raises(NopeInsufficientBalanceError) as exc_info:
            await client.call("evaluate", messages=MESSAGES)
        await client.close()

        err = exc_info.value
        assert err.body is not None
        assert err.body["balance"]["required_mills"] == 3
        assert err.body["topup_url"] == "https://dashboard.nope.net/billing"
        assert err.details == {}

    async def test_non_object_json_gives_body_none(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/evaluate", status=500, text='"boom"')
        client = make(api_key="k")
        with pytest.raises(NopeServerError) as exc_info:
            await client.call("evaluate", messages=MESSAGES)
        await client.close()

        err = exc_info.value
        assert err.body is None
        assert err.response_body == '"boom"'
        assert err.details == {}

    async def test_html_body_gives_body_none(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/evaluate", status=502, text="<html>Bad Gateway</html>")
        client = make(api_key="k")
        with pytest.raises(NopeServerError) as exc_info:
            await client.call("evaluate", messages=MESSAGES)
        await client.close()

        err = exc_info.value
        assert err.body is None
        assert err.response_body == "<html>Bad Gateway</html>"
        assert err.details == {}

    async def test_connection_error_has_no_body(self, client_kind: str) -> None:
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        fake = FakeApi()
        fake.handle = boom  # type: ignore[method-assign]
        client = make_client(client_kind, fake, api_key="k")
        with pytest.raises(NopeConnectionError) as exc_info:
            await client.call("evaluate", messages=MESSAGES)
        await client.close()

        err = exc_info.value
        assert err.body is None
        assert err.response_body is None
        assert err.details == {}


@pytest.mark.parametrize("error_class", ERROR_CLASSES, ids=lambda c: c.__name__)
def test_every_error_class_defaults_body_and_details(error_class: type) -> None:
    err = error_class("message")
    assert err.body is None
    assert err.details == {}


def test_body_is_accepted_by_every_constructor() -> None:
    parsed = {"error": "nope", "extra": 1}
    for error_class in ERROR_CLASSES:
        if error_class is NopeConnectionError:
            continue
        err = error_class("message", body=parsed)
        assert err.body == parsed
