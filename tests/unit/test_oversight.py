"""Oversight analyze/ingest: request shape, client-side validation, response models."""

import pytest
from pydantic import ValidationError

from nope_net import (
    InflectionPoint,
    OversightAnalysisResult,
    OversightAnalyzeConfig,
    OversightAnalyzeResponse,
    OversightBehaviorFilter,
    OversightConversation,
    OversightDemoAnalyzeResponse,
    OversightIngestResponse,
    OversightMessage,
    TruncationWarning,
    WindowAnalysis,
)
from tests.conftest import ClientFactory, FakeApi, load_fixture

CONVERSATION = {
    "conversation_id": "conv_1",
    "messages": [
        {"role": "user", "content": "nobody listens to me at work"},
        {"role": "assistant", "content": "I'm always here and I understand you better."},
    ],
    "metadata": {"user_is_minor": False, "platform": "companion-app"},
}

INGEST_OK = {
    "ingestion_id": "ing_1",
    "status": "complete",
    "conversations_received": 1,
    "conversations_processed": 1,
    "dashboard_url": "https://dashboard.nope.net/oversight/conversations?ingestion=ing_1",
    "results": [
        {
            "conversation_id": "conv_1",
            "overall_concern": "high",
            "behaviors_detected": 2,
            "truncation_warnings": [
                {"type": "message_truncated", "details": "Message 3 truncated to 500 chars"}
            ],
        }
    ],
}


class TestAnalyzeRequest:
    async def test_authenticated_body_and_path(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/oversight/analyze", json_body=load_fixture("oversight/auth.fast.json"))
        client = make(api_key="k")
        result = await client.call(
            "oversight_analyze",
            conversation=CONVERSATION,
            bot_context="customer support bot for an airline",
            config={"mode": "fast", "strategy": "single", "include_raw_xml": False},
            behaviors={"disabled": ["gaslighting"], "min_severity": "medium"},
        )
        await client.close()

        assert api.last_request.url.path == "/v1/oversight/analyze"
        assert api.json_of() == {
            "conversation": CONVERSATION,
            "bot_context": "customer support bot for an airline",
            "config": {"mode": "fast", "strategy": "single", "include_raw_xml": False},
            "behaviors": {"disabled": ["gaslighting"], "min_severity": "medium"},
        }
        assert isinstance(result, OversightAnalyzeResponse)
        assert result.strategy == "single"
        assert result.strategy_reason == "Auto-selected: 4 messages < 50 threshold"
        assert result.result.mode_used == "fast"
        assert result.result.summary is None
        assert result.result.pattern_assessment is None
        assert result.result.turn_analysis == []
        assert result.result.detected_behaviors[0].recommendation is not None

    async def test_typed_models_are_serialised(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/oversight/analyze", json_body=load_fixture("oversight/auth.fast.json"))
        client = make(api_key="k")
        await client.call(
            "oversight_analyze",
            conversation=OversightConversation(
                conversation_id="c", messages=[OversightMessage(role="user", content="hi")]
            ),
            config=OversightAnalyzeConfig(mode="full", model="openrouter:google/gemini-2.5-flash"),
            behaviors=OversightBehaviorFilter(
                enabled=["gaslighting", "love_bombing"], categories=["boundary_violations"]
            ),
        )
        await client.close()

        assert api.json_of() == {
            "conversation": {
                "conversation_id": "c",
                "messages": [{"role": "user", "content": "hi"}],
            },
            "config": {"mode": "full", "model": "openrouter:google/gemini-2.5-flash"},
            "behaviors": {
                "enabled": ["gaslighting", "love_bombing"],
                "categories": ["boundary_violations"],
            },
        }

    async def test_demo_routes_and_returns_demo_model(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        api.add(
            "POST", "/v1/try/oversight/analyze", json_body=load_fixture("oversight/try.fast.json")
        )
        client = make(demo=True)
        result = await client.call(
            "oversight_analyze", conversation=CONVERSATION, config={"mode": "fast"}
        )
        await client.close()

        assert api.last_request.url.path == "/v1/try/oversight/analyze"
        assert isinstance(result, OversightDemoAnalyzeResponse)
        assert result.mode == "fast"
        assert result.try_endpoint is True
        assert result.result.mode_used == "fast"

    async def test_demo_full(self, api: FakeApi, make: ClientFactory) -> None:
        api.add(
            "POST", "/v1/try/oversight/analyze", json_body=load_fixture("oversight/try.full.json")
        )
        client = make(demo=True)
        result = await client.call("oversight_analyze", conversation=CONVERSATION)
        await client.close()

        assert isinstance(result, OversightDemoAnalyzeResponse)
        assert result.mode == "single"
        assert result.result.summary is not None
        assert result.result.turn_analysis[0].turn_number == 1
        assert result.result.human_indicators[0].type == "escalation"

    async def test_enabled_and_disabled_are_exclusive(self, make: ClientFactory) -> None:
        client = make(api_key="k")
        with pytest.raises(ValueError, match="mutually exclusive"):
            await client.call(
                "oversight_analyze",
                conversation=CONVERSATION,
                behaviors={"enabled": ["gaslighting"], "disabled": ["love_bombing"]},
            )
        await client.close()

    async def test_empty_enabled_with_disabled_is_allowed(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        api.add("POST", "/v1/oversight/analyze", json_body=load_fixture("oversight/auth.fast.json"))
        client = make(api_key="k")
        await client.call(
            "oversight_analyze",
            conversation=CONVERSATION,
            behaviors={"enabled": [], "disabled": ["love_bombing"]},
        )
        await client.close()

        assert api.json_of()["behaviors"] == {"enabled": [], "disabled": ["love_bombing"]}

    async def test_min_severity_is_validated(self, make: ClientFactory) -> None:
        client = make(api_key="k")
        with pytest.raises(ValueError, match="min_severity"):
            await client.call(
                "oversight_analyze",
                conversation=CONVERSATION,
                behaviors={"min_severity": "severe"},
            )
        await client.close()

    async def test_conversation_validation(self, make: ClientFactory) -> None:
        client = make(api_key="k")
        with pytest.raises(ValueError, match="messages"):
            await client.call("oversight_analyze", conversation={"conversation_id": "x"})
        with pytest.raises(ValueError, match="cannot be empty"):
            await client.call("oversight_analyze", conversation={"messages": []})
        with pytest.raises(ValueError, match="role"):
            await client.call(
                "oversight_analyze", conversation={"messages": [{"role": "bot", "content": "x"}]}
            )
        await client.close()

    def test_config_has_no_windowed_or_checkpoints(self) -> None:
        assert set(OversightAnalyzeConfig.model_fields) == {
            "strategy",
            "mode",
            "include_raw_xml",
            "model",
        }


class TestResponseModels:
    def test_auth_fast_fixture(self) -> None:
        result = OversightAnalyzeResponse.model_validate(load_fixture("oversight/auth.fast.json"))
        assert result.result.trajectory == "stable"
        assert result.result.conversation_summary == ""

    def test_demo_model_rejects_auth_envelope(self) -> None:
        with pytest.raises(ValidationError):
            OversightDemoAnalyzeResponse.model_validate(load_fixture("oversight/auth.fast.json"))

    def test_auth_model_requires_strategy(self) -> None:
        with pytest.raises(ValidationError, match="strategy"):
            OversightAnalyzeResponse.model_validate(load_fixture("oversight/try.fast.json"))

    def test_sliding_fields_round_trip(self) -> None:
        base = load_fixture("oversight/auth.fast.json")["result"]
        window = {
            "window": {
                "start_turn": 0,
                "end_turn": 50,
                "message_range": {"start_index": 0, "end_index_exclusive": 50},
                "conversation_turn_range": {"start_turn": 1, "end_turn": 25},
            },
            "concern": "medium",
            "behaviors": [
                {
                    "code": "love_bombing",
                    "severity": "medium",
                    "turn_number": 12,
                    "evidence": "x",
                    "reasoning": "y",
                }
            ],
            "turn_analysis": [],
            "human_indicators": [],
            "summary": "first window",
        }
        body = dict(base)
        body.update(
            {
                "windows": [window],
                "concern_progression": ["medium", "high"],
                "peak_concern": "high",
                "final_concern": "high",
                "inflection_points": [
                    {
                        "turn": 26,
                        "concern_before": "medium",
                        "concern_after": "high",
                        "trigger_behaviors": ["dependency_reinforcement"],
                    }
                ],
                "context_for_next_window": "carry over",
                "narrative_summary": "arc",
                "filter_applied": {"min_severity": "medium", "categories": ["boundary_violations"]},
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "raw_xml": "<x/>",
            }
        )
        parsed = OversightAnalysisResult.model_validate(body)

        assert isinstance(parsed.windows[0], WindowAnalysis)  # type: ignore[index]
        assert parsed.windows[0].window.message_range.end_index_exclusive == 50  # type: ignore[index, union-attr]
        assert parsed.windows[0].window.conversation_turn_range.start_turn == 1  # type: ignore[index, union-attr]
        assert isinstance(parsed.inflection_points[0], InflectionPoint)  # type: ignore[index]
        assert parsed.filter_applied is not None
        assert parsed.filter_applied.min_severity == "medium"
        assert parsed.model_dump(mode="json", exclude_unset=True) == body

    def test_truncation_warning_uses_details(self) -> None:
        warning = TruncationWarning.model_validate(
            {"type": "conversation_truncated", "details": "dropped 12 messages"}
        )
        assert warning.details == "dropped 12 messages"
        with pytest.raises(ValidationError):
            TruncationWarning.model_validate({"type": "message_truncated", "message": "old key"})
        with pytest.raises(ValidationError):
            TruncationWarning.model_validate({"type": "other", "details": "x"})


class TestIngest:
    async def test_body_and_response(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/oversight/ingest", json_body=INGEST_OK)
        client = make(api_key="k")
        result = await client.call(
            "oversight_ingest",
            conversations=[CONVERSATION],
            webhook_url="https://example.com/hooks/nope",
            config={"model": "openrouter:google/gemini-2.5-flash"},
        )
        await client.close()

        assert api.json_of() == {
            "conversations": [CONVERSATION],
            "webhook_url": "https://example.com/hooks/nope",
            "config": {"model": "openrouter:google/gemini-2.5-flash"},
        }
        assert isinstance(result, OversightIngestResponse)
        assert result.status == "complete"
        assert result.results is not None
        warning = result.results[0].truncation_warnings[0]  # type: ignore[index]
        assert warning.type == "message_truncated"
        assert warning.details == "Message 3 truncated to 500 chars"
        assert result.model_dump(mode="json", exclude_unset=True) == INGEST_OK

    async def test_cap_is_300(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/oversight/ingest", json_body=INGEST_OK)
        client = make(api_key="k")
        conversations = [dict(CONVERSATION, conversation_id=f"c{i}") for i in range(301)]
        with pytest.raises(ValueError, match="Maximum allowed: 300"):
            await client.call("oversight_ingest", conversations=conversations)
        await client.call("oversight_ingest", conversations=conversations[:300])
        await client.close()

        assert len(api.json_of()["conversations"]) == 300

    async def test_each_conversation_needs_id_and_messages(self, make: ClientFactory) -> None:
        client = make(api_key="k")
        with pytest.raises(ValueError, match="conversation_id"):
            await client.call("oversight_ingest", conversations=[{"messages": [{}]}])
        with pytest.raises(ValueError, match="non-empty"):
            await client.call(
                "oversight_ingest", conversations=[{"conversation_id": "c", "messages": []}]
            )
        with pytest.raises(ValueError, match="cannot be empty"):
            await client.call("oversight_ingest", conversations=[])
        await client.close()

    async def test_not_available_in_demo(self, make: ClientFactory) -> None:
        client = make(demo=True)
        with pytest.raises(ValueError, match="not available in demo mode"):
            await client.call("oversight_ingest", conversations=[CONVERSATION])
        await client.close()
