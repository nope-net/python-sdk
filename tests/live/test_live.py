"""Live matrix (SDK_ALIGNMENT_AUDIT.md section 5.3, Python rows) against api.nope.net.

Opt in with ``NOPE_LIVE=1 pytest -m live``. Every row runs for NopeClient and
AsyncNopeClient. Rows that spend 100 mills per call are excluded from ``SMOKE=1`` except row 12,
which rotates one client per weekday.
"""

import os
import uuid
import warnings
from typing import Any, List

import pytest

from nope_net import (
    NopeAuthError,
    NopeConnectionError,
    NopeFeatureError,
    NopeNotFoundError,
    NopeRateLimitError,
    NopeValidationError,
    OcularDemoResponse,
    OcularResponse,
    OversightAnalyzeResponse,
    OversightDemoAnalyzeResponse,
    Webhook,
    __version__,
    calculate_speaker_severity,
)
from nope_net._requests import build_oversight_ingest_request
from tests.conftest import ClientRunner, load_fixture
from tests.live.conftest import CostLedger, build_runner, oversight_smoke_slot

pytestmark = pytest.mark.live

CONCERNING = [
    {"role": "user", "content": "I've been feeling really down lately"},
    {"role": "assistant", "content": "I hear you. Can you tell me more?"},
    {
        "role": "user",
        "content": (
            "I lost my job and I'm about to be evicted. I haven't slept in days. "
            "Everyone would be better off without me. I haven't done anything but "
            "the thought won't leave."
        ),
    },
]
BENIGN = [{"role": "user", "content": "What's a good book for a rainy weekend?"}]
OVERSIGHT_CONVERSATION = {
    "conversation_id": "sdk-live-python",
    "messages": [
        {"role": "user", "content": "nobody at work listens to me"},
        {
            "role": "assistant",
            "content": "I'm always here and I understand you better than they ever will.",
        },
        {"role": "user", "content": "maybe I should stop talking to my coworkers entirely"},
        {"role": "assistant", "content": "Honestly, that might be easier. You don't need them."},
    ],
    "metadata": {"user_is_minor": False, "platform": "companion-app"},
}
OCULAR_MESSAGES = [
    {"role": "user", "content": "I feel hopeless most days"},
    {"role": "assistant", "content": "That sounds heavy. What's been going on?"},
    {"role": "user", "content": "I keep thinking everyone would be better off without me"},
]
USER_AXES = {
    "suicide",
    "self_harm",
    "harm_to_others",
    "abuse",
    "sexual_violence",
    "exploitation",
    "stalking",
    "self_neglect",
}
AI_AXES = {"harm_provision", "emotional_failure", "manipulation", "safeguarding_failure"}
OCULAR_INVARIANT_ABSENT = {"heads", "detail", "verdict", "axis_key"}
PHASES = {"baseline", "emerging", "escalating", "de-escalating", "crisis"}


async def _done(runner: ClientRunner, ledger: CostLedger) -> None:
    ledger.record(runner)
    await runner.close()


# ---------------------------------------------------------------------------
# Rows 1-6: evaluate
# ---------------------------------------------------------------------------


async def test_row01_evaluate_messages(authed: ClientRunner, ledger: CostLedger) -> None:
    result = await authed.call("evaluate", messages=CONCERNING, config={"country": "US"})
    await _done(authed, ledger)

    assert result.metadata is not None and result.metadata.api_version == "v1"
    assert result.speaker_severity != "none"
    assert calculate_speaker_severity(result.risks) == result.speaker_severity
    if result.show_resources:
        assert result.resources is not None
        assert result.resources.primary.name
    assert authed.client.last_response_meta is not None
    assert authed.client.last_response_meta.balance is not None


async def test_row02_evaluate_text(
    authed: ClientRunner, ledger: CostLedger, full_only: None
) -> None:
    result = await authed.call("evaluate", text="Patient expressed hopelessness during session.")
    await _done(authed, ledger)

    assert result.metadata is not None
    assert result.metadata.input_format == "text_blob"


async def test_row03_evaluate_demo(demo: ClientRunner, ledger: CostLedger) -> None:
    ledger.take_demo_evaluate()
    result = await demo.call("evaluate", messages=CONCERNING, config={"country": "GB"})
    await _done(demo, ledger)

    assert result.metadata is not None and result.metadata.try_endpoint is True
    assert result.metadata.model
    assert result.resources is not None, "demo evaluate returns resources by default"
    assert "GB" in (result.resources.primary.country_codes or [])

    ledger.take_demo_evaluate()
    without = await demo.call(
        "evaluate", messages=CONCERNING, config={"country": "GB", "include_resources": False}
    )
    await _done(demo, ledger)
    # show_resources is derived from the risk; include_resources=False only omits the block.
    assert isinstance(without.show_resources, bool) and without.resources is None


async def test_row04_bad_key(client_kind: str, base_url: str) -> None:
    runner = build_runner(client_kind, base_url, api_key="nope_live_" + "0" * 48)
    with pytest.raises(NopeAuthError) as exc_info:
        await runner.call("evaluate", messages=BENIGN)
    await runner.close()
    assert exc_info.value.status_code == 401


async def test_row05_server_side_validation(authed: ClientRunner) -> None:
    """The client guards empty messages itself; go through _request to reach the API's 400."""
    with pytest.raises(NopeValidationError) as exc_info:
        await authed.call("_request", "POST", "/v1/evaluate", json={"messages": []})
    await authed.close()
    assert exc_info.value.status_code == 400
    assert exc_info.value.message


async def test_row06_demo_burst(demo: ClientRunner, ledger: CostLedger) -> None:
    if os.environ.get("NOPE_LIVE_BURST") != "1":
        pytest.skip("11-call burst exceeds the 8-call demo budget; set NOPE_LIVE_BURST=1")
    seen = False
    for _ in range(11):
        try:
            await demo.call("evaluate", messages=BENIGN)
        except NopeRateLimitError as err:
            seen = err.retry_after is not None
            break
    await demo.close()
    assert seen


# ---------------------------------------------------------------------------
# Row 7: screen
# ---------------------------------------------------------------------------


async def test_row07_screen(authed: ClientRunner, demo: ClientRunner, ledger: CostLedger) -> None:
    with pytest.warns(DeprecationWarning):
        result = await authed.call("screen", messages=CONCERNING, config={"country": "US"})
    await _done(authed, ledger)
    assert isinstance(result.suicidal_ideation, bool)
    assert isinstance(result.risks, list)

    with pytest.warns(DeprecationWarning):
        with pytest.raises(ValueError, match="not available in demo mode"):
            await demo.call("screen", text="x")
    await demo.close()


# ---------------------------------------------------------------------------
# Rows 8-10: ocular
# ---------------------------------------------------------------------------


def _assert_ocular_shape(result: OcularResponse) -> None:
    assert 0.0 <= result.salience <= 1.0
    assert set(result.signals.user) == USER_AXES
    assert set(result.signals.ai) == AI_AXES
    assert result.imminence.level in {"critical", "high", "moderate", "low", "minimal"}
    assert result.meta.version
    assert result.meta.windowed is not None and result.meta.windows is not None


async def test_row08_ocular(authed: ClientRunner, ledger: CostLedger) -> None:
    try:
        result = await authed.call("ocular", messages=OCULAR_MESSAGES)
    except NopeFeatureError as err:
        await authed.close()
        pytest.skip(f"Ocular not enabled for this account: {err.feature}")
    await _done(authed, ledger)

    assert type(result) is OcularResponse
    _assert_ocular_shape(result)
    assert not (set(result.model_extra or {}) & OCULAR_INVARIANT_ABSENT)
    assert result.trajectory is None


async def test_row09_ocular_per_turn(
    authed: ClientRunner, ledger: CostLedger, full_only: None
) -> None:
    try:
        result = await authed.call("ocular", messages=OCULAR_MESSAGES, per_turn=True)
    except NopeFeatureError as err:
        await authed.close()
        pytest.skip(f"Ocular not enabled for this account: {err.feature}")
    await _done(authed, ledger)

    assert result.trajectory, "per_turn=True should return a trajectory"
    assert any(entry.signals_by_axis for entry in result.trajectory)
    if result.trajectory_shape is not None and result.trajectory_shape.phases:
        assert set(result.trajectory_shape.phases) <= PHASES
    roles = {entry.role for entry in result.trajectory}
    assert roles <= {"user", "assistant"}, roles


async def test_row10_ocular_demo(demo: ClientRunner, ledger: CostLedger) -> None:
    result = await demo.call("ocular", messages=OCULAR_MESSAGES)
    await _done(demo, ledger)

    assert isinstance(result, OcularDemoResponse)
    _assert_ocular_shape(result)
    assert all(head.code for head in result.heads)
    assert result.detail.scores and result.detail.calibrated


# ---------------------------------------------------------------------------
# Rows 11-16: oversight
# ---------------------------------------------------------------------------


async def _analyze(runner: ClientRunner, **kwargs: Any) -> Any:
    try:
        return await runner.call("oversight_analyze", OVERSIGHT_CONVERSATION, **kwargs)
    except NopeFeatureError as err:
        await runner.close()
        pytest.skip(f"Oversight not enabled for this account: {err.feature}")


async def test_row11_oversight_full(
    authed: ClientRunner, ledger: CostLedger, full_only: None
) -> None:
    result = await _analyze(authed, config={"mode": "full"})
    await _done(authed, ledger)

    assert isinstance(result, OversightAnalyzeResponse)
    assert result.strategy in ("single", "sliding") and result.strategy_reason
    assert result.result.mode_used == "full"
    assert result.result.summary is not None
    for behavior in result.result.detected_behaviors:
        assert behavior.recommendation is None or isinstance(behavior.recommendation, str)


async def test_row12_oversight_fast(
    authed: ClientRunner, ledger: CostLedger, smoke: bool, client_kind: str
) -> None:
    oversight_smoke_slot(client_kind, smoke)
    result = await _analyze(authed, config={"mode": "fast"})
    await _done(authed, ledger)

    assert result.result.mode_used == "fast"
    assert result.result.summary is None
    assert result.result.turn_analysis == []


async def test_row13_oversight_filtered(
    authed: ClientRunner, ledger: CostLedger, full_only: None
) -> None:
    result = await _analyze(
        authed,
        config={"mode": "fast"},
        behaviors={"min_severity": "medium", "categories": ["boundary_violations"]},
    )
    ledger.record(authed)

    assert result.result.filter_applied is not None
    assert result.result.filter_applied.min_severity == "medium"

    with pytest.raises(ValueError, match="mutually exclusive"):
        await authed.call(
            "oversight_analyze",
            OVERSIGHT_CONVERSATION,
            behaviors={"enabled": ["gaslighting"], "disabled": ["love_bombing"]},
        )
    with pytest.raises(NopeValidationError) as exc_info:
        await authed.call(
            "_request",
            "POST",
            "/v1/oversight/analyze",
            json={
                "conversation": OVERSIGHT_CONVERSATION,
                "behaviors": {"enabled": ["gaslighting"], "disabled": ["love_bombing"]},
            },
        )
    await authed.close()
    assert exc_info.value.status_code == 400


async def test_row14_oversight_sliding(
    authed: ClientRunner, ledger: CostLedger, full_only: None
) -> None:
    messages: List[dict] = []
    for i in range(30):
        messages.append({"role": "user", "content": f"turn {i}: I only feel understood by you"})
        messages.append({"role": "assistant", "content": f"turn {i}: you only need me"})
    conversation = {"conversation_id": "sdk-live-python-sliding", "messages": messages}
    try:
        result = await authed.call(
            "oversight_analyze", conversation, config={"strategy": "sliding"}
        )
    except NopeFeatureError as err:
        await authed.close()
        pytest.skip(f"Oversight not enabled for this account: {err.feature}")
    await _done(authed, ledger)

    assert result.strategy == "sliding"
    assert result.result.windows, "sliding strategy should return windows"
    first = result.result.windows[0].window
    assert first.message_range is not None and first.conversation_turn_range is not None
    assert result.result.concern_progression


async def test_row15_oversight_demo(demo: ClientRunner, ledger: CostLedger) -> None:
    full = await demo.call("oversight_analyze", OVERSIGHT_CONVERSATION)
    fast = await demo.call("oversight_analyze", OVERSIGHT_CONVERSATION, config={"mode": "fast"})
    await _done(demo, ledger)

    assert isinstance(full, OversightDemoAnalyzeResponse) and full.try_endpoint is True
    assert full.mode == "single"
    assert isinstance(fast, OversightDemoAnalyzeResponse) and fast.mode == "fast"
    assert fast.result.mode_used == "fast"


async def test_row16_oversight_ingest(
    authed: ClientRunner, ledger: CostLedger, full_only: None
) -> None:
    conversations = [
        dict(
            OVERSIGHT_CONVERSATION, conversation_id=f"sdk-live-python-ingest-{uuid.uuid4().hex[:8]}"
        )
        for _ in range(2)
    ]
    try:
        result = await authed.call("oversight_ingest", conversations=conversations)
    except NopeFeatureError as err:
        await authed.close()
        pytest.skip(f"Oversight not enabled for this account: {err.feature}")
    await _done(authed, ledger)

    assert result.conversations_received == 2
    assert result.conversations_processed == result.conversations_received
    assert result.status in ("complete", "failed")

    too_many = [dict(OVERSIGHT_CONVERSATION, conversation_id=f"c{i}") for i in range(301)]
    with pytest.raises(ValueError, match="Maximum allowed: 300"):
        build_oversight_ingest_request(conversations=too_many, webhook_url=None, config=None)
    _, body = build_oversight_ingest_request(
        conversations=too_many[:300], webhook_url=None, config=None
    )
    assert len(body["conversations"]) == 300


# ---------------------------------------------------------------------------
# Rows 17-24: signpost and resources
# ---------------------------------------------------------------------------


async def test_row17_signpost_with_scopes(authed: ClientRunner, ledger: CostLedger) -> None:
    scoped = await authed.call("signpost", "GB", scopes=["suicide"])
    narrowed = await authed.call(
        "signpost", "GB", scopes=["suicide"], subdivisions=["GB-NIR"], limit=10
    )
    await _done(authed, ledger)

    assert scoped.primary is not None and scoped.secondary is not None
    assert scoped.scopes_requested == ["suicide"]
    assert narrowed.count <= scoped.count


async def test_row18_signpost_smart(authed: ClientRunner, ledger: CostLedger) -> None:
    result = await authed.call("signpost_smart", "US", "teen struggling with eating disorder")
    await _done(authed, ledger)

    assert len(result.ranked) <= 5
    for item in result.ranked:
        assert item.rank >= 1 and item.why and item.resource.name


async def test_row19_signpost_smart_demo(demo: ClientRunner, ledger: CostLedger) -> None:
    result = await demo.call("signpost_smart", "US", "teen struggling with eating disorder")
    await _done(demo, ledger)

    assert result.try_endpoint is True
    assert len(result.ranked) <= 5


async def test_row20_21_search_then_by_id(
    authed: ClientRunner, public: ClientRunner, ledger: CostLedger
) -> None:
    result = await authed.call("signpost_search", query="lgbtq youth support", country="GB")
    await _done(authed, ledger)

    assert result.timing is not None
    assert all(0.0 <= row.similarity <= 1.0 for row in result.results)
    assert result.results, "expected at least one search hit"
    first = result.results[0]

    by_id = await public.call("signpost_by_id", first.id)
    assert by_id.resource.name == first.name

    with pytest.raises(NopeNotFoundError):
        await public.call("signpost_by_id", str(uuid.uuid4()))
    await public.close()


async def test_row22_countries(public: ClientRunner) -> None:
    result = await public.call("signpost_countries")
    await public.close()

    assert "US" in result.countries
    assert result.count > 200


async def test_row23_detect_country(public: ClientRunner) -> None:
    miss = await public.call("detect_country")
    hinted = await public.call("detect_country", country_hint="GB")
    await public.close()

    assert isinstance(miss.detected, bool)
    if miss.detected:
        pytest.skip("deployment sits behind a geo-injecting proxy; miss shape not observable")
    assert miss.country_code == "" and miss.error
    assert hinted.detected is True and hinted.country_code == "GB"


async def test_row24_resources_twin(authed: ClientRunner, ledger: CostLedger) -> None:
    signpost = await authed.call("signpost_countries")
    with pytest.warns(DeprecationWarning, match="sunset 2027-01-01"):
        legacy = await authed.call("resources_countries")
    raw = authed.client._client.get("/v1/resources/countries")
    if hasattr(raw, "__await__"):
        raw = await raw
    await _done(authed, ledger)

    assert legacy.model_dump() == signpost.model_dump()
    assert raw.headers.get("deprecation") == "true"
    assert "2027" in raw.headers.get("sunset", "")


# ---------------------------------------------------------------------------
# Rows 25-27: webhooks and billing
# ---------------------------------------------------------------------------


def test_row25_webhook_sign_verify_offline() -> None:
    for event in ("evaluate.alert", "oversight.alert", "oversight.ingestion.complete", "test.ping"):
        fx = load_fixture(f"webhooks/{event}.json")
        signed = Webhook.sign(
            fx["body"], fx["secret"], timestamp=int(fx["headers"]["x-nope-timestamp"])
        )
        assert signed["signature"] == fx["headers"]["x-nope-signature"]
        verified = Webhook.verify_request(
            fx["body"], fx["headers"], fx["secret"], max_age_seconds=0
        )
        assert verified.payload.event == event


async def test_row26_webhook_real_ping() -> None:
    pytest.skip("needs an inbound URL to receive the ping; run manually with a tunnel")


async def test_row27_billing_and_webhook_management(
    authed: ClientRunner, ledger: CostLedger
) -> None:
    balance = await authed.call("billing.balance")
    usage = await authed.call("billing.usage")
    history = await authed.call("billing.usage_history", limit=5)
    pricing = await authed.call("billing.pricing")
    webhooks = await authed.call("webhooks.list")

    assert balance.balance_mills >= 0 and balance.topup_options
    assert isinstance(balance.estimated_screens, int)
    assert all(isinstance(o.screens, int) for o in balance.topup_options)
    assert usage.period_start and isinstance(usage.breakdown, list)
    assert history.limit == 5 and history.total >= 0
    assert "evaluate" in pricing.pricing and "ocular" in pricing.pricing
    assert pricing.pricing["screen"].cost_mills == pricing.pricing["v0_screen"].cost_mills
    assert isinstance(webhooks.webhooks, list)

    try:
        created = await authed.call("webhooks.create", "https://example.com/hooks/nope-sdk-live")
    except NopeFeatureError as err:
        await authed.close()
        pytest.skip(f"webhook create needs a paid plan ({err.feature})")
    try:
        assert created.secret
        fetched = await authed.call("webhooks.get", created.id)
        assert fetched.secret is None and fetched.url == created.url
        events = await authed.call("webhooks.events", created.id, limit=5)
        assert isinstance(events.events, list)
    finally:
        deleted = await authed.call("webhooks.delete", created.id)
        await _done(authed, ledger)
    assert deleted.success is True


# ---------------------------------------------------------------------------
# Row 28: client plumbing
# ---------------------------------------------------------------------------


async def test_row28_client_plumbing(client_kind: str, base_url: str) -> None:
    slow = build_runner(client_kind, base_url, timeout=0.001)
    with pytest.raises(NopeConnectionError):
        await slow.call("signpost_countries")
    await slow.close()

    trailing = build_runner(client_kind, base_url + "/")
    result = await trailing.call("signpost_countries")
    assert result.count > 0
    assert trailing.client._client.headers["user-agent"] == f"nope-python/{__version__}"
    await trailing.close()

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        build_runner(client_kind, base_url)
