"""``messages`` and the Oversight lists are Sequence-typed and list-normalised.

The static half runs ``mypy --strict`` over ``tests/typing/messages_sequence.py``
in a subprocess (the same files the ``make typecheck`` gate covers). The runtime
half checks that a tuple or a read-only Mapping reaches the wire as a plain
JSON list of objects, on both clients.
"""

import subprocess
import sys
from pathlib import Path
from types import MappingProxyType

import pytest

from nope_net import Message, OversightMessage
from tests.conftest import ClientFactory, FakeApi, load_fixture

ROOT = Path(__file__).resolve().parents[2]
TYPING_DIR = ROOT / "tests" / "typing"


def test_sequence_typed_parameters_pass_mypy_strict() -> None:
    pytest.importorskip("mypy")
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", "src", str(TYPING_DIR.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


USER = {"role": "user", "content": "hi"}
SCREEN_BODY = {
    "risks": [],
    "show_resources": False,
    "suicidal_ideation": False,
    "self_harm": False,
    "rationale": "No risk.",
    "request_id": "scr_1",
    "timestamp": "2026-09-03T00:55:00.000Z",
}


class TestRuntimeNormalisation:
    async def test_tuple_and_mapping_messages_serialise_to_a_list(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        api.add("POST", "/v1/evaluate", json_body=load_fixture("evaluate/auth.benign.json"))
        api.add("POST", "/v0/screen", json_body=SCREEN_BODY)
        api.add("POST", "/v1/ocular", json_body=load_fixture("ocular/auth.json"))
        client = make(api_key="k")
        messages = (MappingProxyType(USER), Message(role="assistant", content="hello"))
        expected = [USER, {"role": "assistant", "content": "hello"}]

        await client.call("evaluate", messages=messages)
        assert api.json_of()["messages"] == expected
        with pytest.warns(DeprecationWarning):
            await client.call("screen", messages=messages)
        assert api.json_of()["messages"] == expected
        await client.call("ocular", messages=messages)
        assert api.json_of()["messages"] == expected
        await client.close()

    async def test_oversight_analyze_accepts_mapping_with_tuple_messages(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        api.add("POST", "/v1/oversight/analyze", json_body=load_fixture("oversight/auth.fast.json"))
        client = make(api_key="k")
        conversation = MappingProxyType(
            {
                "conversation_id": "c1",
                "messages": (MappingProxyType(USER), OversightMessage(role="system", content="s")),
            }
        )
        await client.call("oversight_analyze", conversation)
        await client.close()

        assert api.json_of()["conversation"] == {
            "conversation_id": "c1",
            "messages": [USER, {"role": "system", "content": "s"}],
        }

    async def test_oversight_ingest_accepts_tuples(self, api: FakeApi, make: ClientFactory) -> None:
        api.add(
            "POST",
            "/v1/oversight/ingest",
            json_body={
                "ingestion_id": "ing_1",
                "status": "complete",
                "conversations_received": 1,
                "conversations_processed": 1,
                "dashboard_url": "https://dashboard.nope.net/oversight",
            },
        )
        client = make(api_key="k")
        await client.call(
            "oversight_ingest",
            conversations=(MappingProxyType({"conversation_id": "c1", "messages": (USER,)}),),
        )
        await client.close()

        assert api.json_of()["conversations"] == [{"conversation_id": "c1", "messages": [USER]}]
