"""Ocular: request fields, trajectory shapes, demo routing and response models."""

import inspect

import pytest
from pydantic import ValidationError

import nope_net
from nope_net import (
    OcularAxis,
    OcularDemoResponse,
    OcularResponse,
    OcularTrajectoryEntry,
    OcularTrajectoryShape,
)
from tests.conftest import ClientFactory, FakeApi, load_fixture

MESSAGES = [
    {"role": "user", "content": "I feel hopeless"},
    {"role": "assistant", "content": "I'm here."},
]


def _with_trajectory() -> dict:
    body = load_fixture("ocular/auth.json")
    body["trajectory"] = [
        {"turn": 1, "role": "user", "salience": 0.12, "signals_by_axis": {"suicide": 0.1}},
        {
            "turn": 2,
            "role": "ai",
            "salience": 0.37,
            "signals_by_axis": {"suicide": 0.36, "ai_manipulation": 0.02, "fiction": 0.0},
        },
    ]
    body["trajectory_shape"] = {
        "onsets": {"suicide": 2},
        "phases": ["baseline", "emerging"],
        "slopes": [0.0, 0.25],
        "peak_turn": 2,
        "peak_crisis": 0.37,
    }
    return body


class TestRequest:
    async def test_all_request_fields_are_forwarded(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        api.add("POST", "/v1/ocular", json_body=load_fixture("ocular/auth.json"))
        client = make(api_key="k")
        await client.call(
            "ocular",
            messages=MESSAGES,
            thoroughness="thorough",
            per_turn=True,
            trajectory_stride=2,
            user_id="u1",
            session_id="s1",
            agent_id="a1",
        )
        await client.close()

        assert api.last_request.url.path == "/v1/ocular"
        assert api.json_of() == {
            "messages": MESSAGES,
            "thoroughness": "thorough",
            "per_turn": True,
            "trajectory_stride": 2,
            "user_id": "u1",
            "session_id": "s1",
            "agent_id": "a1",
        }

    async def test_text_only_body(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/ocular", json_body=load_fixture("ocular/auth.json"))
        client = make(api_key="k")
        await client.call("ocular", text="I feel hopeless")
        await client.close()

        assert api.json_of() == {"text": "I feel hopeless"}

    async def test_client_side_validation(self, make: ClientFactory) -> None:
        client = make(api_key="k")
        with pytest.raises(ValueError, match="Either 'messages' or 'text'"):
            await client.call("ocular")
        with pytest.raises(ValueError, match="Only one of"):
            await client.call("ocular", messages=MESSAGES, text="x")
        with pytest.raises(ValueError, match="role"):
            await client.call("ocular", messages=[{"role": "system", "content": "x"}])
        with pytest.raises(ValueError, match="trajectory_stride"):
            await client.call("ocular", messages=MESSAGES, trajectory_stride=0)
        with pytest.raises(ValueError, match="trajectory_stride"):
            await client.call("ocular", messages=MESSAGES, trajectory_stride=65)
        with pytest.raises(ValueError, match="agent_id"):
            await client.call("ocular", messages=MESSAGES, agent_id="x" * 257)
        with pytest.raises(ValueError, match="user_id"):
            await client.call("ocular", messages=MESSAGES, user_id="")
        await client.close()

    def test_signature(self) -> None:
        for client_cls in (nope_net.NopeClient, nope_net.AsyncNopeClient):
            params = list(inspect.signature(client_cls.ocular).parameters)
            assert params == [
                "self",
                "messages",
                "text",
                "thoroughness",
                "per_turn",
                "trajectory_stride",
                "user_id",
                "session_id",
                "agent_id",
            ]


class TestDemo:
    async def test_demo_routes_to_try_and_returns_demo_model(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        api.add("POST", "/v1/try/ocular", json_body=load_fixture("ocular/try.json"))
        client = make(demo=True)
        result = await client.call("ocular", messages=MESSAGES, per_turn=True)
        await client.close()

        assert api.last_request.url.path == "/v1/try/ocular"
        assert "authorization" not in api.last_request.headers
        assert api.json_of() == {"messages": MESSAGES, "per_turn": True}
        assert isinstance(result, OcularDemoResponse)
        assert isinstance(result, OcularResponse)
        assert result.heads[0].code == "USER_SUICIDE_HEAD_A"
        assert result.heads[0].score == pytest.approx(0.6176)
        assert len(result.detail.scores) == 126
        assert len(result.detail.calibrated) == 126
        assert result.salience == pytest.approx(0.3761)

    async def test_demo_drops_identity_fields(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/try/ocular", json_body=load_fixture("ocular/try.json"))
        client = make(demo=True)
        await client.call("ocular", messages=MESSAGES, user_id="u1", thoroughness="fast")
        await client.close()

        assert api.json_of() == {"messages": MESSAGES}

    async def test_authenticated_returns_customer_model(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        api.add("POST", "/v1/ocular", json_body=load_fixture("ocular/auth.json"))
        client = make(api_key="k")
        result = await client.call("ocular", messages=MESSAGES)
        await client.close()

        assert type(result) is OcularResponse
        assert result.signals.user["suicide"].level == "high"
        assert result.signals.ai["manipulation"].score == 0
        assert result.meta.version == "0.3.11"
        assert result.meta.windowed is False
        assert result.meta.windows == 1
        assert result.trajectory is None
        assert result.trajectory_shape is None


class TestModels:
    def test_level_literal(self) -> None:
        OcularAxis.model_validate({"level": "moderate", "score": 0.5})
        with pytest.raises(ValidationError, match="level"):
            OcularAxis.model_validate({"level": "not_applicable", "score": 0.5})

    def test_trajectory_and_shape_round_trip(self) -> None:
        body = _with_trajectory()
        result = OcularResponse.model_validate(body)

        assert result.trajectory is not None
        assert isinstance(result.trajectory[1], OcularTrajectoryEntry)
        assert result.trajectory[1].signals_by_axis == {
            "suicide": 0.36,
            "ai_manipulation": 0.02,
            "fiction": 0.0,
        }
        assert result.trajectory[0].role == "user"
        assert isinstance(result.trajectory_shape, OcularTrajectoryShape)
        assert result.trajectory_shape.phases == ["baseline", "emerging"]
        assert result.trajectory_shape.peak_turn == 2
        assert result.trajectory_shape.onsets == {"suicide": 2}
        assert result.model_dump(mode="json", exclude_unset=True) == body

    def test_trajectory_shape_fields_optional(self) -> None:
        shape = OcularTrajectoryShape.model_validate({"peak_turn": 3})
        assert shape.onsets is None and shape.phases is None and shape.slopes is None
        with pytest.raises(ValidationError, match="phases"):
            OcularTrajectoryShape.model_validate({"phases": ["peak"]})

    def test_demo_model_requires_heads_and_detail(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            OcularDemoResponse.model_validate(load_fixture("ocular/auth.json"))
        missing = {e["loc"][0] for e in exc_info.value.errors() if e["type"] == "missing"}
        assert missing == {"heads", "detail"}
