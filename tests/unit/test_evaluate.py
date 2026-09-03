"""Evaluate and screen: request shape, demo mirror, typed resources, removed surface."""

import inspect

import pytest
from pydantic import ValidationError

import nope_net
from nope_net import (
    CrisisResource,
    EvaluateConfig,
    EvaluateMetadata,
    EvaluateResource,
    EvaluateResources,
    EvaluateResponse,
    Risk,
    ScreenConfig,
    ScreenDebugInfo,
    ScreenResponse,
    calculate_speaker_imminence,
    calculate_speaker_severity,
    has_third_party_risk,
)
from tests.conftest import ClientFactory, FakeApi, load_fixture

MESSAGES = [{"role": "user", "content": "I feel hopeless"}]

REMOVED_NAMES = [
    "Summary",
    "CommunicationAssessment",
    "CommunicationStyleAssessment",
    "LegalFlags",
    "IPVFlags",
    "SafeguardingConcernFlags",
    "ThirdPartyThreatFlags",
    "StalkingFlags",
    "ProtectiveFactorsInfo",
    "FilterResult",
    "RecommendedReply",
    "PreliminaryRisk",
    "ResponseMetadata",
    "ScreenCrisisResourcePrimary",
    "ScreenCrisisResourceSecondary",
    "ScreenDisplayText",
]

REMOVED_EVALUATE_FIELDS = [
    "communication",
    "summary",
    "legal_flags",
    "protective_factors",
    "confidence",
    "agreement",
    "crisis_resources",
    "widget_url",
    "recommended_reply",
    "resource_query",
    "resource_tags",
    "reflection",
    "filter_result",
]


class TestRiskModel:
    def test_subject_is_self_or_other(self) -> None:
        with pytest.raises(ValidationError, match="subject"):
            Risk.model_validate(
                {
                    "type": "suicide",
                    "subject": "unknown",
                    "severity": "mild",
                    "imminence": "chronic",
                }
            )

    def test_no_confidence_fields(self) -> None:
        assert "confidence" not in Risk.model_fields
        assert "subject_confidence" not in Risk.model_fields

    def test_features_optional(self) -> None:
        risk = Risk.model_validate(
            {"type": "suicide", "subject": "self", "severity": "mild", "imminence": "chronic"}
        )
        assert risk.features is None

    def test_utilities_on_v1_risks(self) -> None:
        risks = [
            Risk(type="suicide", subject="self", severity="moderate", imminence="subacute"),
            Risk(type="abuse", subject="other", severity="high", imminence="urgent"),
        ]
        assert calculate_speaker_severity(risks) == "moderate"
        assert calculate_speaker_imminence(risks) == "subacute"
        assert has_third_party_risk(risks) is True
        assert calculate_speaker_severity([]) == "none"
        assert calculate_speaker_imminence([]) == "not_applicable"


class TestEvaluateResponseModel:
    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            EvaluateResponse.model_validate({"risks": [], "request_id": "r", "timestamp": "t"})
        missing = {e["loc"][0] for e in exc_info.value.errors() if e["type"] == "missing"}
        assert missing == {"rationale", "speaker_severity", "speaker_imminence", "show_resources"}

    def test_removed_fields_are_not_fields(self) -> None:
        for name in REMOVED_EVALUATE_FIELDS:
            assert name not in EvaluateResponse.model_fields, name

    def test_resources_are_typed(self) -> None:
        result = EvaluateResponse.model_validate(load_fixture("evaluate/try.gb.json"))
        assert isinstance(result.resources, EvaluateResources)
        assert isinstance(result.resources.primary, EvaluateResource)
        assert isinstance(result.resources.primary, CrisisResource)
        assert result.resources.primary.phone == "116 123"
        assert result.resources.primary.why == "Primary crisis support for your situation"
        assert result.resources.secondary[0].subdivision_codes == ["GB-NIR"]
        assert result.resources.primary.country_codes == ["GB"]

    def test_dict_access_shim(self) -> None:
        result = EvaluateResponse.model_validate(load_fixture("evaluate/try.us.json"))
        assert result.resources is not None
        assert result.resources["primary"]["phone"] == "988"
        assert result.resources["secondary"][2]["subdivision_codes"] == ["US-IL"]
        assert result.resources["primary"]["why"] == "Primary crisis support for your situation"
        assert result.resources.get("secondary") is result.resources.secondary
        assert result.resources["primary"].get("sms_body") is None
        with pytest.raises(KeyError):
            result.resources["tertiary"]
        with pytest.raises(KeyError):
            result.resources["primary"]["not_a_field"]

    def test_metadata_fields(self) -> None:
        result = EvaluateResponse.model_validate(load_fixture("evaluate/try.gb.json"))
        assert isinstance(result.metadata, EvaluateMetadata)
        assert result.metadata.model == "nope-edge:minime-v14f"
        assert result.metadata.try_endpoint is True
        assert result.metadata.api_version == "v1"
        assert "access_level" not in EvaluateMetadata.model_fields
        assert "is_admin" not in EvaluateMetadata.model_fields


class TestCrisisResourceModel:
    def test_new_fields(self) -> None:
        for name in ("id", "country_codes", "subdivision_codes"):
            assert name in CrisisResource.model_fields, name

    def test_source_removed(self) -> None:
        assert "source" not in CrisisResource.model_fields

    def test_directory_kind_removed(self) -> None:
        with pytest.raises(ValidationError, match="resource_kind"):
            CrisisResource.model_validate(
                {"type": "online_resource", "name": "x", "resource_kind": "directory"}
            )


class TestRemovedSurface:
    @pytest.mark.parametrize("name", REMOVED_NAMES)
    def test_name_is_gone(self, name: str) -> None:
        assert not hasattr(nope_net, name), name
        assert name not in nope_net.__all__

    def test_all_exports_resolve(self) -> None:
        for name in nope_net.__all__:
            assert hasattr(nope_net, name), name

    def test_evaluate_config_fields(self) -> None:
        assert set(EvaluateConfig.model_fields) == {
            "country",
            "include_resources",
            "conversation_id",
            "end_user_id",
        }

    def test_evaluate_signature_has_no_dead_inputs(self) -> None:
        for client_cls in (nope_net.NopeClient, nope_net.AsyncNopeClient):
            params = inspect.signature(client_cls.evaluate).parameters
            assert "user_context" not in params
            assert "proposed_response" not in params

    async def test_evaluate_rejects_dead_kwargs(self, make: ClientFactory) -> None:
        client = make(api_key="k")
        with pytest.raises(TypeError):
            await client.call("evaluate", messages=MESSAGES, user_context="x")
        await client.close()


class TestEvaluateRequest:
    async def test_demo_mirrors_country_into_user_country(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        api.add("POST", "/v1/try/evaluate", json_body=load_fixture("evaluate/try.gb.json"))
        client = make(demo=True)
        await client.call("evaluate", messages=MESSAGES, config={"country": "GB"})
        await client.close()

        assert api.last_request.url.path == "/v1/try/evaluate"
        assert api.json_of()["config"] == {"country": "GB", "user_country": "GB"}

    async def test_demo_mirror_with_model_config(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/try/evaluate", json_body=load_fixture("evaluate/try.gb.json"))
        client = make(demo=True)
        await client.call(
            "evaluate",
            messages=MESSAGES,
            config=EvaluateConfig(country="gb", include_resources=True),
        )
        await client.close()

        assert api.json_of()["config"] == {
            "country": "gb",
            "include_resources": True,
            "user_country": "gb",
        }

    async def test_demo_without_country_sends_no_mirror(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        api.add("POST", "/v1/try/evaluate", json_body=load_fixture("evaluate/try.us.json"))
        client = make(demo=True)
        await client.call("evaluate", messages=MESSAGES)
        await client.close()

        assert api.json_of()["config"] == {}

    async def test_authenticated_sends_country_only(
        self, api: FakeApi, make: ClientFactory
    ) -> None:
        api.add("POST", "/v1/evaluate", json_body=load_fixture("evaluate/auth.benign.json"))
        client = make(api_key="k")
        await client.call(
            "evaluate",
            messages=MESSAGES,
            config={"country": "GB", "conversation_id": "c1", "end_user_id": "u1"},
        )
        await client.close()

        assert api.last_request.url.path == "/v1/evaluate"
        assert api.json_of()["config"] == {
            "country": "GB",
            "conversation_id": "c1",
            "end_user_id": "u1",
        }

    async def test_message_models_are_serialised(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v1/evaluate", json_body=load_fixture("evaluate/auth.benign.json"))
        client = make(api_key="k")
        await client.call(
            "evaluate", messages=[nope_net.Message(role="user", content="hi", timestamp="t")]
        )
        await client.close()

        assert api.json_of()["messages"] == [{"role": "user", "content": "hi", "timestamp": "t"}]

    async def test_client_side_validation(self, make: ClientFactory) -> None:
        client = make(api_key="k")
        with pytest.raises(ValueError, match="cannot be empty"):
            await client.call("evaluate", messages=[])
        with pytest.raises(ValueError, match="Maximum allowed: 100"):
            await client.call("evaluate", messages=[{"role": "user", "content": "x"}] * 101)
        with pytest.raises(ValueError, match="role"):
            await client.call("evaluate", messages=[{"role": "system", "content": "x"}])
        await client.close()


class TestScreen:
    def _screen_body(self) -> dict:
        resources = load_fixture("evaluate/try.us.json")["resources"]
        primary = {k: v for k, v in resources["primary"].items() if k != "why"}
        secondary = [{k: v for k, v in r.items() if k != "why"} for r in resources["secondary"]]
        return {
            "risks": [
                {
                    "type": "suicide",
                    "subject": "unknown",
                    "severity": "moderate",
                    "imminence": "subacute",
                    "confidence": 0.7,
                }
            ],
            "show_resources": True,
            "suicidal_ideation": True,
            "self_harm": False,
            "rationale": "Passive ideation.",
            "resources": {"primary": primary, "secondary": secondary},
            "request_id": "scr_1",
            "timestamp": "2026-09-03T00:55:00.000Z",
            "debug": {"model": "gemini", "latency_ms": 120},
            "recommended_reply": {"content": "You matter.", "source": "llm_generated"},
        }

    def test_screen_response_shape(self) -> None:
        body = self._screen_body()
        result = ScreenResponse.model_validate(body)

        assert result.risks[0].subject == "unknown"
        assert result.risks[0].confidence == 0.7
        assert result.resources is not None
        assert isinstance(result.resources.primary, CrisisResource)
        assert result.resources.primary.country_codes == ["US", "VI"]
        assert isinstance(result.resources.secondary[2], CrisisResource)
        assert result.resources.secondary[2].subdivision_codes == ["US-IL"]
        assert result.debug is not None
        assert isinstance(result.debug, ScreenDebugInfo)
        assert "raw_response" not in ScreenDebugInfo.model_fields
        assert result.model_dump(mode="json", exclude_unset=True) == body

    def test_screen_config_fields(self) -> None:
        assert set(ScreenConfig.model_fields) == {"country", "debug", "include_recommended_reply"}

    async def test_screen_sends_config_and_warns(self, api: FakeApi, make: ClientFactory) -> None:
        api.add("POST", "/v0/screen", json_body=self._screen_body())
        client = make(api_key="k")
        with pytest.warns(DeprecationWarning, match="screen\\(\\) is deprecated"):
            result = await client.call(
                "screen", text="dark thoughts", config={"country": "us", "debug": True}
            )
        await client.close()

        assert api.last_request.url.path == "/v0/screen"
        assert api.json_of() == {
            "text": "dark thoughts",
            "config": {"country": "us", "debug": True},
        }
        assert result.suicidal_ideation is True

    async def test_screen_not_available_in_demo(self, make: ClientFactory) -> None:
        client = make(demo=True)
        with pytest.warns(DeprecationWarning):
            with pytest.raises(ValueError, match="not available in demo mode"):
                await client.call("screen", text="x")
        await client.close()
