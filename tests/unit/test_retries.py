"""Retry policy: 429 and 503 only, Retry-After honoured, injected sleep, never on timeouts."""

from typing import List

import httpx
import pytest

from nope_net import (
    AsyncNopeClient,
    NopeClient,
    NopeConnectionError,
    NopeRateLimitError,
    NopeServerError,
    NopeServiceUnavailableError,
)
from tests.conftest import CannedResponse, FakeApi, load_derived, load_fixture, make_client

MESSAGES = [{"role": "user", "content": "hello"}]
OK = load_fixture("evaluate/auth.benign.json")


def _429(headers: dict = {}, body: dict = {"error": "rate_limit_exceeded"}) -> CannedResponse:  # noqa: B006
    return CannedResponse(429, json_body=body, headers=headers)


def _503(headers: dict = {}, body: dict = {"error": "service_unavailable"}) -> CannedResponse:  # noqa: B006
    return CannedResponse(503, json_body=body, headers=headers)


def test_default_max_retries_is_two() -> None:
    with NopeClient(api_key="k") as client:
        assert client.max_retries == 2
    assert AsyncNopeClient(api_key="k").max_retries == 2


async def test_429_then_200_uses_retry_after_header(client_kind: str) -> None:
    fake = FakeApi().queue(_429({"Retry-After": "7"}), CannedResponse(200, json_body=OK))
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k")

    result = await client.call("evaluate", messages=MESSAGES)
    await client.close()

    assert result.speaker_severity == "none"
    assert len(fake.requests) == 2
    assert sleeps == [7.0]


async def test_429_body_retry_after_seconds_fallback(client_kind: str) -> None:
    body, _ = load_derived("429.rate-limit.json")
    body["retry_after_seconds"] = 3
    fake = FakeApi().queue(_429(body=body), CannedResponse(200, json_body=OK))
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k")

    await client.call("evaluate", messages=MESSAGES)
    await client.close()

    assert sleeps == [3.0]


async def test_exponential_backoff_without_hints(client_kind: str) -> None:
    fake = FakeApi().queue(_429(), _429(), CannedResponse(200, json_body=OK))
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k")

    await client.call("evaluate", messages=MESSAGES)
    await client.close()

    assert sleeps == [1.0, 2.0]
    assert len(fake.requests) == 3


async def test_wait_is_capped_at_30_seconds(client_kind: str) -> None:
    fake = FakeApi().queue(_429({"Retry-After": "120"}), CannedResponse(200, json_body=OK))
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k")

    await client.call("evaluate", messages=MESSAGES)
    await client.close()

    assert sleeps == [30.0]


async def test_exhausted_retries_raise_last_error(client_kind: str) -> None:
    fake = FakeApi().queue(_429({"Retry-After": "1"}), _429({"Retry-After": "1"}), _429())
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k")

    with pytest.raises(NopeRateLimitError):
        await client.call("evaluate", messages=MESSAGES)
    await client.close()

    assert len(fake.requests) == 3
    assert sleeps == [1.0, 1.0]


async def test_503_is_retried(client_kind: str) -> None:
    body, headers = load_derived("503.service-unavailable.json")
    fake = FakeApi().queue(_503(headers, body), CannedResponse(200, json_body=OK))
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k")

    await client.call("evaluate", messages=MESSAGES)
    await client.close()

    assert sleeps == [5.0]
    assert len(fake.requests) == 2


async def test_503_exhaustion_raises_service_unavailable(client_kind: str) -> None:
    fake = FakeApi().queue(_503(), _503(), _503())
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k")

    with pytest.raises(NopeServiceUnavailableError):
        await client.call("evaluate", messages=MESSAGES)
    await client.close()

    assert len(fake.requests) == 3


async def test_500_is_not_retried(client_kind: str) -> None:
    fake = FakeApi().queue(
        CannedResponse(500, json_body={"error": "Internal server error"}),
        CannedResponse(200, json_body=OK),
    )
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k")

    with pytest.raises(NopeServerError):
        await client.call("evaluate", messages=MESSAGES)
    await client.close()

    assert len(fake.requests) == 1
    assert sleeps == []


async def test_502_is_not_retried(client_kind: str) -> None:
    fake = FakeApi().queue(
        CannedResponse(502, text="Bad Gateway"), CannedResponse(200, json_body=OK)
    )
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k")

    with pytest.raises(NopeServerError):
        await client.call("evaluate", messages=MESSAGES)
    await client.close()

    assert len(fake.requests) == 1


async def test_timeout_is_not_retried(client_kind: str) -> None:
    calls: List[int] = []

    def slow(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ReadTimeout("slow", request=request)

    fake = FakeApi()
    fake.handle = slow  # type: ignore[method-assign]
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k")

    with pytest.raises(NopeConnectionError):
        await client.call("evaluate", messages=MESSAGES)
    await client.close()

    assert calls == [1]
    assert sleeps == []


async def test_connection_error_is_not_retried(client_kind: str) -> None:
    calls: List[int] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ConnectError("refused", request=request)

    fake = FakeApi()
    fake.handle = refuse  # type: ignore[method-assign]
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k")

    with pytest.raises(NopeConnectionError):
        await client.call("evaluate", messages=MESSAGES)
    await client.close()

    assert calls == [1]
    assert sleeps == []


async def test_max_retries_zero_disables(client_kind: str) -> None:
    fake = FakeApi().queue(_429({"Retry-After": "1"}), CannedResponse(200, json_body=OK))
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k", max_retries=0)

    with pytest.raises(NopeRateLimitError):
        await client.call("evaluate", messages=MESSAGES)
    await client.close()

    assert len(fake.requests) == 1
    assert sleeps == []


async def test_retry_reissues_identical_request(client_kind: str) -> None:
    fake = FakeApi().queue(_429({"Retry-After": "1"}), CannedResponse(200, json_body=OK))
    sleeps: List[float] = []
    client = make_client(client_kind, fake, sleeps=sleeps, api_key="k")

    await client.call("evaluate", messages=MESSAGES, config={"country": "GB"})
    await client.close()

    first, second = fake.requests
    assert first.method == second.method == "POST"
    assert first.url == second.url
    assert first.content == second.content
