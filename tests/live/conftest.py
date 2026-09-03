"""Live-suite plumbing: opt-in gate, key loader, demo budget, cost ledger.

Nothing here prints, logs or stores the API key. The key comes from
``NOPE_E2E_API_KEY``; when that is unset the loader reads
``NOPE_DEDICATED_CI_KEY`` from ``../api/.env`` at runtime if that file exists.

Run with ``NOPE_LIVE=1 pytest -m live`` (``SMOKE=1`` for the nightly subset).
The whole suite runs serially in one process and makes at most 8 demo
evaluate calls per run (the demo route shares a 10/min per-IP bucket).
"""

import datetime as _dt
import os
import re
from pathlib import Path
from typing import Any, List, Optional

import pytest

from nope_net import AsyncNopeClient, NopeClient
from tests.conftest import ClientRunner

DEFAULT_BASE_URL = "https://api.nope.net"
DEMO_EVALUATE_BUDGET = 8
_ENV_FILE = Path(__file__).resolve().parents[3] / "api" / ".env"


def _read_env_file_key(name: str) -> Optional[str]:
    if not _ENV_FILE.is_file():
        return None
    pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(name)}\s*=\s*(.*?)\s*$")
    for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            value = match.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value or None
    return None


def load_api_key() -> Optional[str]:
    """``NOPE_E2E_API_KEY`` first, else ``NOPE_DEDICATED_CI_KEY`` from ``../api/.env``."""
    return os.environ.get("NOPE_E2E_API_KEY") or _read_env_file_key("NOPE_DEDICATED_CI_KEY")


class CostLedger:
    """Accumulates ``X-Cost-Mills`` from every response the suite received."""

    def __init__(self) -> None:
        self.billed_calls = 0
        self.total_mills = 0.0
        self.demo_evaluate_calls = 0

    def record(self, runner: ClientRunner) -> None:
        meta = runner.client.last_response_meta
        if meta is not None and meta.balance is not None and meta.balance.cost_mills:
            self.billed_calls += 1
            self.total_mills += meta.balance.cost_mills

    def take_demo_evaluate(self) -> None:
        if self.demo_evaluate_calls >= DEMO_EVALUATE_BUDGET:
            pytest.skip(f"demo evaluate budget of {DEMO_EVALUATE_BUDGET} calls per run spent")
        self.demo_evaluate_calls += 1


_LEDGER = CostLedger()


@pytest.fixture(scope="session", autouse=True)
def _live_gate() -> None:
    if os.environ.get("NOPE_LIVE") != "1":
        pytest.fail(
            "The live suite calls api.nope.net and spends balance. Set NOPE_LIVE=1 to run it."
        )


@pytest.fixture(scope="session")
def api_key() -> str:
    key = load_api_key()
    if not key:
        pytest.fail("No API key: set NOPE_E2E_API_KEY or put NOPE_DEDICATED_CI_KEY in ../api/.env")
    return key


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("NOPE_API_URL", DEFAULT_BASE_URL)


@pytest.fixture(scope="session")
def smoke() -> bool:
    return os.environ.get("SMOKE") == "1"


@pytest.fixture
def full_only(smoke: bool) -> None:
    if smoke:
        pytest.skip("full matrix only (SMOKE=1 runs the nightly subset)")


@pytest.fixture(scope="session")
def ledger() -> CostLedger:
    return _LEDGER


@pytest.fixture(params=["sync", "async"])
def client_kind(request: pytest.FixtureRequest) -> str:
    return str(request.param)


def build_runner(kind: str, base_url: str, **kwargs: Any) -> ClientRunner:
    if kind == "async":
        return ClientRunner(kind, AsyncNopeClient(base_url=base_url, **kwargs))
    return ClientRunner(kind, NopeClient(base_url=base_url, **kwargs))


@pytest.fixture
def authed(client_kind: str, api_key: str, base_url: str) -> ClientRunner:
    return build_runner(client_kind, base_url, api_key=api_key, timeout=120.0)


@pytest.fixture
def demo(client_kind: str, base_url: str) -> ClientRunner:
    return build_runner(client_kind, base_url, demo=True, timeout=120.0)


@pytest.fixture
def public(client_kind: str, base_url: str) -> ClientRunner:
    return build_runner(client_kind, base_url, timeout=60.0)


def oversight_smoke_slot(kind: str, smoke: bool) -> None:
    """Row 12 (Oversight fast, 100 mills) runs for one client per weekday in smoke mode.

    Rotation: Monday Node, Tuesday Python sync, Wednesday Python async, and so on.
    """
    if not smoke:
        return
    slot = _dt.date.today().weekday() % 3
    expected = {0: "node", 1: "sync", 2: "async"}[slot]
    if expected != kind:
        pytest.skip(f"smoke rotation: today's Oversight fast slot is {expected}")


def pytest_terminal_summary(terminalreporter: Any) -> None:
    ledger = _LEDGER
    if ledger.billed_calls == 0 and ledger.demo_evaluate_calls == 0:
        return
    dollars = ledger.total_mills / 1000
    terminalreporter.write_sep(
        "-",
        f"live cost: {ledger.total_mills:g} mills (${dollars:.4f}) across "
        f"{ledger.billed_calls} billed calls; demo evaluate calls: "
        f"{ledger.demo_evaluate_calls}/{DEMO_EVALUATE_BUDGET}",
    )


__all__: List[str] = ["CostLedger", "build_runner", "load_api_key", "oversight_smoke_slot"]
