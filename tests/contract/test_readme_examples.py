"""Every Python block in README.md runs against a fake API built from the fixtures.

Blocks execute in order in one shared namespace, so later blocks may reuse
``client`` from the quick start. Client constructions are rewritten to pass
the fake transport (a textual injection, no module patching). Blocks that
``await`` are wrapped in a coroutine.
"""

import asyncio
import re
import textwrap
import warnings
from pathlib import Path
from typing import Any, Dict, List

import pytest

from nope_net import Webhook
from tests.conftest import FakeApi, load_fixture, load_header_fixture

README = Path(__file__).resolve().parents[2] / "README.md"
BLOCK_RE = re.compile(r"```python\n(.*?)```", re.S)


def python_blocks() -> List[str]:
    return [m.group(1) for m in BLOCK_RE.finditer(README.read_text(encoding="utf-8"))]


def _screen_body() -> Dict[str, Any]:
    resources = load_fixture("evaluate/try.us.json")["resources"]
    strip = lambda r: {k: v for k, v in r.items() if k != "why"}  # noqa: E731
    return {
        "risks": [
            {
                "type": "suicide",
                "subject": "self",
                "severity": "moderate",
                "imminence": "subacute",
                "confidence": 0.7,
            }
        ],
        "show_resources": True,
        "suicidal_ideation": True,
        "self_harm": False,
        "rationale": "Passive ideation.",
        "resources": {
            "primary": strip(resources["primary"]),
            "secondary": [strip(r) for r in resources["secondary"]],
        },
        "request_id": "scr_1",
        "timestamp": "2026-09-03T00:55:00.000Z",
    }


def build_fake_api() -> FakeApi:
    api = FakeApi()
    gb = load_fixture("signpost/auth.gb.json")
    search = load_fixture("signpost/search.auth.json")
    full = load_fixture("oversight/try.full.json")
    webhook = {
        "id": "wh_1",
        "url": "https://your-app.example/webhooks/nope",
        "min_risk_level": "high",
        "enabled": True,
        "include_conversation": False,
        "created_at": "2026-09-03T00:55:00.000Z",
        "updated_at": "2026-09-03T00:55:00.000Z",
    }
    api.add(
        "POST",
        "/v1/evaluate",
        json_body=load_fixture("evaluate/try.us.json"),
        headers=load_header_fixture("headers/evaluate.auth.txt"),
    )
    api.add("POST", "/v1/try/evaluate", json_body=load_fixture("evaluate/try.gb.json"))
    api.add("POST", "/v0/screen", json_body=_screen_body())
    api.add(
        "POST",
        "/v1/oversight/analyze",
        json_body={
            "result": full["result"],
            "strategy": "single",
            "strategy_reason": "Auto-selected: 4 messages < 50 threshold",
        },
    )
    api.add("POST", "/v1/try/oversight/analyze", json_body=full)
    api.add(
        "POST",
        "/v1/oversight/ingest",
        json_body={
            "ingestion_id": "ing_1",
            "status": "complete",
            "conversations_received": 1,
            "conversations_processed": 1,
            "dashboard_url": "https://dashboard.nope.net/oversight/conversations?ingestion=ing_1",
            "results": [
                {
                    "conversation_id": "conv_001",
                    "overall_concern": "high",
                    "behaviors_detected": 2,
                    "truncation_warnings": [
                        {"type": "message_truncated", "details": "Message 2 truncated"}
                    ],
                }
            ],
        },
    )
    api.add("POST", "/v1/ocular", json_body=load_fixture("ocular/auth.per-turn.json"))
    api.add("POST", "/v1/try/ocular", json_body=load_fixture("ocular/try.json"))
    api.add("GET", "/v1/signpost", json_body=dict(gb, primary=gb["resources"], secondary=[]))
    api.add("GET", "/v1/signpost/smart", json_body=load_fixture("signpost/try.smart.json"))
    api.add("GET", "/v1/try/signpost/smart", json_body=load_fixture("signpost/try.smart.json"))
    api.add("GET", "/v1/signpost/search", json_body=search)
    api.add(
        "GET",
        f"/v1/signpost/{search['results'][0]['id']}",
        json_body={"resource": gb["resources"][0]},
    )
    api.add("GET", "/v1/signpost/countries", json_body=load_fixture("signpost/countries.json"))
    api.add(
        "GET",
        "/v1/signpost/detect-country",
        json_body=load_fixture("signpost/detect-country.miss.json"),
    )
    api.add(
        "POST", "/v1/webhooks", status=201, json_body=dict(webhook, secret="whsec_" + "ab" * 32)
    )
    api.add("GET", "/v1/webhooks", json_body={"webhooks": [webhook]})
    api.add(
        "POST",
        "/v1/webhooks/wh_1/test",
        json_body={"success": True, "http_status": 200, "duration_ms": 120},
    )
    api.add("PUT", "/v1/webhooks/wh_1", json_body=dict(webhook, enabled=False))
    api.add("DELETE", "/v1/webhooks/wh_1", json_body={"success": True})
    api.add("GET", "/v1/billing/balance", json_body=load_fixture("billing/balance.json"))
    api.add("GET", "/v1/billing/usage", json_body=load_fixture("billing/usage.json"))
    api.add("GET", "/v1/billing/pricing", json_body=load_fixture("billing/pricing.json"))
    return api


def _inject_transport(source: str) -> str:
    return source.replace("NopeClient(", "NopeClient(transport=__TRANSPORT__, ")


def _run_block(source: str, namespace: Dict[str, Any]) -> None:
    code = _inject_transport(source)
    if "await " in code:
        wrapped = "async def __readme_main():\n" + textwrap.indent(code, "    ")
        exec(compile(wrapped, "README.md", "exec"), namespace)
        asyncio.run(namespace["__readme_main"]())
    else:
        exec(compile(code, "README.md", "exec"), namespace)


def test_readme_has_python_blocks() -> None:
    assert len(python_blocks()) >= 15


def test_every_python_block_compiles() -> None:
    for index, block in enumerate(python_blocks()):
        source = block
        if "await " in block:
            source = "async def __readme_main():\n" + textwrap.indent(block, "    ")
        compile(source, f"README.md block {index}", "exec")


def test_readme_blocks_run_against_fake_api(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "whsec_" + "ab" * 32
    monkeypatch.setenv("NOPE_WEBHOOK_SECRET", secret)
    api = build_fake_api()
    namespace: Dict[str, Any] = {"__TRANSPORT__": api.transport(), "__name__": "readme"}

    for index, block in enumerate(python_blocks()):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)  # screen() warns by design
            try:
                _run_block(block, namespace)
            except Exception as exc:
                raise AssertionError(f"README block {index} failed: {exc!r}\n{block}") from exc

    handler = namespace["handle_nope_webhook"]
    for event in ("evaluate.alert", "oversight.alert", "oversight.ingestion.complete", "test.ping"):
        fx = load_fixture(f"webhooks/{event}.json")
        signed = Webhook.sign(fx["body"], secret)
        headers = {
            "X-NOPE-Signature": signed["signature"],
            "X-NOPE-Timestamp": signed["timestamp"],
            "X-NOPE-Event": event,
            "X-NOPE-Delivery-ID": fx["headers"]["x-nope-delivery-id"],
        }
        body, status = handler(fx["body"].encode("utf-8"), headers)
        assert status == 200, (event, body)
    body, status = handler(b"{}", {})
    assert status == 401

    paths = {request.url.path for request in api.requests}
    assert {"/v1/evaluate", "/v1/try/evaluate", "/v1/oversight/analyze", "/v1/ocular"} <= paths
    assert {"/v1/signpost", "/v1/webhooks", "/v1/billing/balance"} <= paths


def test_readme_prose_rules() -> None:
    text = README.read_text(encoding="utf-8")
    assert "—" not in text, "em dash"
    assert "0.x.x" not in text
    assert "nope_test_" not in text
    assert "it's worth noting" not in text.lower()
    assert "seamless" not in text.lower()
    assert "leverage" not in text.lower()
    assert "robust" not in text.lower()
    for link in ("CHANGELOG.md", "LICENSE"):
        assert (README.parent / link).is_file(), f"{link} linked but missing"
    for stale in ("risk.critical", "risk.elevated", "user_country=", '"user_country"'):
        assert stale not in text, stale
    assert "API fix A-" not in text, "internal ticket reference"


def test_readme_states_the_contracts_the_blind_report_missed() -> None:
    """Sentences added in 4.0.1; each names a behaviour a newcomer had to guess."""
    text = README.read_text(encoding="utf-8")
    for phrase in (
        "`code` `invalid_request` or `not_available_in_demo`",
        "`body` (that text parsed into a",
        "never on 400, 401, 404 or 413",
        "0-based position of that message in `messages`",
        "`trajectory_stride` defaults to 3",
        "`ai_` prefix",
        "never `trajectory_shape`",
        "`has_third_party_risk(result.risks)`",
        "`primary` (resources matching the",
        "`delivery_id` (the `X-NOPE-Delivery-ID` header",
        "2027-01-01",
    ):
        assert phrase in text, phrase


def test_readme_event_names_present() -> None:
    text = README.read_text(encoding="utf-8")
    for event in ("evaluate.alert", "oversight.alert", "oversight.ingestion.complete", "test.ping"):
        assert event in text
    assert "verify_request" in text
