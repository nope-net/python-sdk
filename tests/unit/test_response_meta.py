"""client.last_response_meta: rate-limit and balance headers from the last response."""

from nope_net import AsyncNopeClient, BalanceMeta, NopeClient, RateLimitMeta, ResponseMeta
from nope_net._http import parse_response_meta
from tests.conftest import (
    ClientFactory,
    FakeApi,
    load_derived,
    load_fixture,
    load_header_fixture,
)

MESSAGES = [{"role": "user", "content": "hello"}]


def test_meta_is_none_before_any_call() -> None:
    with NopeClient(api_key="k") as client:
        assert client.last_response_meta is None
    assert AsyncNopeClient(api_key="k").last_response_meta is None


async def test_paid_route_headers(api: FakeApi, make: ClientFactory) -> None:
    headers = load_header_fixture("headers/evaluate.auth.txt")
    api.add(
        "POST",
        "/v1/evaluate",
        json_body=load_fixture("evaluate/auth.benign.json"),
        headers=headers,
    )
    client = make(api_key="k")
    await client.call("evaluate", messages=MESSAGES)
    meta = client.client.last_response_meta
    await client.close()

    assert meta == ResponseMeta(
        rate_limit=RateLimitMeta(limit=2000, remaining=1999, reset=1788396960000),
        balance=BalanceMeta(balance_mills=12345.6, cost_mills=3.0),
    )


async def test_demo_route_headers_have_no_balance(api: FakeApi, make: ClientFactory) -> None:
    headers = load_header_fixture("headers/evaluate.try.txt")
    api.add(
        "POST",
        "/v1/try/evaluate",
        json_body=load_fixture("evaluate/try.us.json"),
        headers=headers,
    )
    client = make(demo=True)
    await client.call("evaluate", messages=MESSAGES)
    meta = client.client.last_response_meta
    await client.close()

    assert meta is not None
    assert meta.rate_limit == RateLimitMeta(limit=10, remaining=9, reset=1788396960000)
    assert meta.balance is None


async def test_no_headers_gives_empty_meta(api: FakeApi, make: ClientFactory) -> None:
    api.add("GET", "/v1/signpost/countries", json_body=load_fixture("signpost/countries.json"))
    client = make()
    await client.call("signpost_countries")
    meta = client.client.last_response_meta
    await client.close()

    assert meta == ResponseMeta(rate_limit=None, balance=None)


async def test_meta_is_set_on_error_responses(api: FakeApi, make: ClientFactory) -> None:
    body, headers = load_derived("402.evaluate.json")
    api.add("POST", "/v1/evaluate", status=402, json_body=body, headers=headers)
    client = make(api_key="k")
    try:
        await client.call("evaluate", messages=MESSAGES)
    except Exception:
        pass
    meta = client.client.last_response_meta
    await client.close()

    assert meta is not None
    assert meta.balance == BalanceMeta(balance_mills=0.0, cost_mills=3.0)


def test_parse_ignores_unparsable_values() -> None:
    meta = parse_response_meta({"X-RateLimit-Limit": "lots", "X-Balance-Mills": "12.5"})
    assert meta.rate_limit == RateLimitMeta(limit=None, remaining=None, reset=None)
    assert meta.balance == BalanceMeta(balance_mills=12.5, cost_mills=None)


def test_parse_header_names_are_case_insensitive() -> None:
    meta = parse_response_meta({"x-ratelimit-remaining": "5", "X-COST-MILLS": "0.1"})
    assert meta.rate_limit is not None
    assert meta.rate_limit.remaining == 5
    assert meta.balance is not None
    assert meta.balance.cost_mills == 0.1
