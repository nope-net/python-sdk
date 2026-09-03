"""Shared test helpers.

Offline tests never touch the network: every client under test is built with an
``httpx.MockTransport`` handed in through the public ``transport`` option, so the
SDK's own request path (headers, routing, retries, error parsing) is what runs.

``FakeApi`` records requests and serves canned responses. ``ClientRunner`` lets a
single test body exercise both ``NopeClient`` and ``AsyncNopeClient``.
"""

import inspect
import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Union

import httpx
import pytest

from nope_net import AsyncNopeClient, NopeClient

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(relative_path: str) -> Any:
    """Load a JSON fixture from ``tests/fixtures``."""
    with (FIXTURES_DIR / relative_path).open(encoding="utf-8") as fh:
        return json.load(fh)


DERIVED_DIR = Path(__file__).parent / "unit" / "fixtures_derived"


def load_derived(name: str) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """Load a source-derived error body: returns ``(body, headers)`` minus the ``_`` keys."""
    with (DERIVED_DIR / name).open(encoding="utf-8") as fh:
        raw = json.load(fh)
    headers = dict(raw.get("_headers", {}))
    body = {k: v for k, v in raw.items() if not k.startswith("_")}
    return body, headers


def load_header_fixture(relative_path: str) -> Dict[str, str]:
    """Load a ``headers/*.txt`` fixture (``name: value`` per line)."""
    headers: Dict[str, str] = {}
    for line in (FIXTURES_DIR / relative_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, _, value = line.partition(":")
        headers[name.strip()] = value.strip()
    return headers


class CannedResponse:
    """One response the fake API will serve."""

    def __init__(
        self,
        status: int = 200,
        *,
        json_body: Any = None,
        text: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.status = status
        self.json_body = json_body
        self.text = text
        self.headers = headers or {}

    def to_httpx(self) -> httpx.Response:
        if self.text is not None:
            return httpx.Response(self.status, text=self.text, headers=self.headers)
        return httpx.Response(self.status, json=self.json_body, headers=self.headers)


class FakeApi:
    """Canned API keyed by ``(METHOD, path)``, plus an ordered queue for retry tests.

    The queue, when non-empty, wins over routes so a test can script
    "429 then 200" without caring about the path.
    """

    def __init__(self) -> None:
        self.requests: List[httpx.Request] = []
        self._routes: Dict[Tuple[str, str], CannedResponse] = {}
        self._queue: List[CannedResponse] = []

    def add(
        self,
        method: str,
        path: str,
        *,
        status: int = 200,
        json_body: Any = None,
        text: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> "FakeApi":
        self._routes[(method.upper(), path)] = CannedResponse(
            status, json_body=json_body, text=text, headers=headers
        )
        return self

    def queue(self, *responses: CannedResponse) -> "FakeApi":
        self._queue.extend(responses)
        return self

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self._queue:
            return self._queue.pop(0).to_httpx()
        canned = self._routes.get((request.method.upper(), request.url.path))
        if canned is None:
            return httpx.Response(
                404, json={"error": f"no canned response for {request.method} {request.url.path}"}
            )
        return canned.to_httpx()

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    @property
    def last_request(self) -> httpx.Request:
        return self.requests[-1]

    def json_of(self, index: int = -1) -> Any:
        return json.loads(self.requests[index].content.decode("utf-8"))


@pytest.fixture
def api() -> FakeApi:
    return FakeApi()


SleepRecorder = List[float]


class ClientRunner:
    """Uniform wrapper so one test runs against both client flavours.

    ``call("webhooks.create", ...)`` resolves dotted attribute paths on the
    client; async results are awaited, sync results returned as-is.
    """

    def __init__(self, kind: str, client: Union[NopeClient, AsyncNopeClient]) -> None:
        self.kind = kind
        self.client = client

    @property
    def is_async(self) -> bool:
        return self.kind == "async"

    async def call(self, dotted: str, *args: Any, **kwargs: Any) -> Any:
        target: Any = self.client
        for part in dotted.split("."):
            target = getattr(target, part)
        result = target(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def close(self) -> None:
        result = self.client.close()
        if inspect.isawaitable(result):
            await result


def make_client(
    kind: str,
    fake: FakeApi,
    *,
    sleeps: Optional[SleepRecorder] = None,
    **kwargs: Any,
) -> ClientRunner:
    """Build a sync or async client wired to ``fake`` with an injected sleep."""
    if sleeps is not None:
        if kind == "async":

            async def async_sleep(seconds: float) -> None:
                sleeps.append(seconds)

            kwargs["sleep"] = async_sleep
        else:

            def sync_sleep(seconds: float) -> None:
                sleeps.append(seconds)

            kwargs["sleep"] = sync_sleep
    if kind == "async":
        return ClientRunner(kind, AsyncNopeClient(transport=fake.transport(), **kwargs))
    return ClientRunner(kind, NopeClient(transport=fake.transport(), **kwargs))


@pytest.fixture(params=["sync", "async"])
def client_kind(request: pytest.FixtureRequest) -> str:
    return str(request.param)


ClientFactory = Callable[..., ClientRunner]


@pytest.fixture
def make(client_kind: str, api: FakeApi) -> ClientFactory:
    """Factory fixture: ``make(api_key="k", demo=True)`` -> ClientRunner for this kind."""

    def factory(**kwargs: Any) -> ClientRunner:
        return make_client(client_kind, api, **kwargs)

    return factory


__all__ = [
    "Awaitable",
    "CannedResponse",
    "ClientFactory",
    "ClientRunner",
    "DERIVED_DIR",
    "FIXTURES_DIR",
    "FakeApi",
    "load_derived",
    "load_fixture",
    "load_header_fixture",
    "make_client",
]
