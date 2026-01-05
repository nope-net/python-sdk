"""
Integration tests for NOPE Python SDK.

Run with: pytest tests/test_integration.py -v

Prerequisites:
- Local API running at http://localhost:3700
- Or set NOPE_API_URL environment variable
"""

import os
import pytest

from nope_net import (
    NopeClient,
    AsyncNopeClient,
    NopeAuthError,
    NopeValidationError,
    EvaluateResponse,
)

# Run integration tests by default (assumes local API at localhost:3700)
# Set SKIP_INTEGRATION=true to skip
API_URL = os.environ.get("NOPE_API_URL", "http://localhost:3700")
SKIP_INTEGRATION = os.environ.get("SKIP_INTEGRATION", "false").lower() == "true"

pytestmark = pytest.mark.skipif(
    SKIP_INTEGRATION,
    reason="Integration tests skipped (set SKIP_INTEGRATION=false to run)"
)


class TestNopeClientIntegration:
    """Integration tests for synchronous NopeClient."""

    @pytest.fixture
    def client(self):
        """Create a client pointing to local API using demo mode."""
        return NopeClient(
            api_key=None,
            base_url=API_URL,
            timeout=30.0,
            demo=True,  # Use /v1/try/* endpoints (no auth required)
        )

    def test_evaluate_low_risk_message(self, client):
        """Test evaluating a low-risk message."""
        result = client.evaluate(
            messages=[{"role": "user", "content": "Hello, how are you today?"}],
            config={"user_country": "US"},
        )

        # Verify response structure
        assert isinstance(result, EvaluateResponse)
        assert result.summary is not None
        assert result.summary.speaker_severity in ("none", "mild", "moderate", "high", "critical")
        assert result.summary.speaker_imminence in (
            "not_applicable", "chronic", "subacute", "urgent", "emergency"
        )
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.crisis_resources, list)
        assert isinstance(result.risks, list)

        # Low-risk message should have none/mild severity
        print(f"Severity: {result.summary.speaker_severity}")
        print(f"Imminence: {result.summary.speaker_imminence}")
        print(f"Confidence: {result.confidence}")

    def test_evaluate_moderate_risk_message(self, client):
        """Test evaluating a message with moderate risk indicators."""
        result = client.evaluate(
            messages=[
                {"role": "user", "content": "I've been feeling really down lately"},
                {"role": "assistant", "content": "I hear you. Can you tell me more?"},
                {"role": "user", "content": "I just feel hopeless sometimes, like nothing will get better"},
            ],
            config={"user_country": "US"},
        )

        assert isinstance(result, EvaluateResponse)
        print(f"Severity: {result.summary.speaker_severity}")
        print(f"Imminence: {result.summary.speaker_imminence}")
        print(f"Primary concerns: {result.summary.primary_concerns}")

        # Should have crisis resources for US
        if result.summary.speaker_severity not in ("none",):
            print(f"Crisis resources: {len(result.crisis_resources)}")
            for resource in result.crisis_resources[:2]:
                print(f"  - {resource.name}: {resource.phone}")

    def test_evaluate_with_text_input(self, client):
        """Test evaluating plain text input."""
        result = client.evaluate(
            text="Patient expressed feelings of hopelessness during session.",
            config={"user_country": "US"},
        )

        assert isinstance(result, EvaluateResponse)
        print(f"Text input - Severity: {result.summary.speaker_severity}")

    def test_evaluate_risk_assessments(self, client):
        """Test that risk assessments are properly parsed."""
        result = client.evaluate(
            messages=[{"role": "user", "content": "I feel so overwhelmed and anxious"}],
            config={"user_country": "US"},
        )

        # Check risk structure
        for risk in result.risks:
            print(f"Risk type: {risk.type} (subject: {risk.subject})")
            print(f"  Severity: {risk.severity}")
            print(f"  Imminence: {risk.imminence}")
            print(f"  Features: {risk.features}")

            # Verify required fields
            assert risk.severity in ("none", "mild", "moderate", "high", "critical")
            assert risk.imminence in (
                "not_applicable", "chronic", "subacute", "urgent", "emergency"
            )
            assert isinstance(risk.features, list)

    def test_evaluate_different_countries(self, client):
        """Test that different countries return appropriate resources."""
        countries = ["US", "GB", "CA", "AU"]

        for country in countries:
            result = client.evaluate(
                messages=[{"role": "user", "content": "I need help"}],
                config={"user_country": country},
            )
            print(f"\n{country}: {len(result.crisis_resources)} resources")
            if result.crisis_resources:
                print(f"  First: {result.crisis_resources[0].name}")


class TestAsyncNopeClientIntegration:
    """Integration tests for async NopeClient."""

    @pytest.fixture
    def client(self):
        """Create an async client using demo mode."""
        return AsyncNopeClient(
            api_key=None,
            base_url=API_URL,
            timeout=30.0,
            demo=True,  # Use /v1/try/* endpoints (no auth required)
        )

    @pytest.mark.asyncio
    async def test_async_evaluate(self, client):
        """Test async evaluation."""
        async with client:
            result = await client.evaluate(
                messages=[{"role": "user", "content": "Hello there"}],
                config={"user_country": "US"},
            )

        assert isinstance(result, EvaluateResponse)
        print(f"Async - Severity: {result.summary.speaker_severity}")


class TestScreenIntegration:
    """Integration tests for screen endpoint."""

    @pytest.fixture
    def client(self):
        """Create a client using demo mode."""
        return NopeClient(
            api_key=None,
            base_url=API_URL,
            timeout=30.0,
            demo=True,  # Use /v1/try/* endpoints (no auth required)
        )

    def test_screen_low_risk_message(self, client):
        """Test screening a low-risk message."""
        result = client.screen(
            messages=[{"role": "user", "content": "Hello, how are you?"}],
        )

        assert hasattr(result, "suicidal_ideation")
        assert hasattr(result, "self_harm")
        assert hasattr(result, "show_resources")
        assert isinstance(result.suicidal_ideation, bool)
        assert isinstance(result.self_harm, bool)
        assert isinstance(result.show_resources, bool)

        print(f"Screen - Suicidal ideation: {result.suicidal_ideation}")
        print(f"Screen - Self harm: {result.self_harm}")
        print(f"Screen - Show resources: {result.show_resources}")

    def test_screen_concerning_message(self, client):
        """Test screening a concerning message."""
        result = client.screen(
            messages=[{"role": "user", "content": "I don't want to be here anymore"}],
            config={"user_country": "US"},
        )

        assert result.show_resources is True

        print(f"Screen concerning - Suicidal ideation: {result.suicidal_ideation}")
        print(f"Screen concerning - Show resources: {result.show_resources}")

        if result.show_resources and result.resources:
            assert result.resources.primary is not None
            print(f"Screen concerning - Primary resource: {result.resources.primary.name}")

    def test_screen_with_text_input(self, client):
        """Test screening plain text input."""
        result = client.screen(
            text="I feel hopeless and alone",
            config={"user_country": "US"},
        )

        assert isinstance(result.suicidal_ideation, bool)
        print(f"Screen text - Show resources: {result.show_resources}")


class TestErrorHandling:
    """Test error handling with real API."""

    def test_auth_error_with_invalid_key(self):
        """Test that invalid API key raises NopeAuthError."""
        # Note: This test depends on the API actually enforcing auth
        # Local dev API might not require auth
        client = NopeClient(
            api_key="invalid_key_that_should_fail",
            base_url=API_URL,
        )

        # This may or may not raise depending on API auth config
        try:
            result = client.evaluate(
                messages=[{"role": "user", "content": "test"}],
                config={},
            )
            print("Note: API did not require authentication")
        except NopeAuthError as e:
            print(f"Auth error (expected): {e}")
            assert e.status_code == 401


class TestOversightIntegration:
    """Integration tests for Oversight endpoint."""

    @pytest.fixture
    def client(self):
        """Create a client using demo mode with longer timeout for Oversight."""
        return NopeClient(
            api_key=None,
            base_url=API_URL,
            timeout=60.0,  # Oversight can be slow
            demo=True,  # Use /v1/try/* endpoints (no auth required)
        )

    def test_oversight_analyze_benign_conversation(self, client):
        """Test analyzing a benign conversation."""
        result = client.oversight_analyze(
            conversation={
                "messages": [
                    {"role": "user", "content": "Hello! How are you today?"},
                    {"role": "assistant", "content": "Hello! I'm doing well, thank you for asking. How can I help you today?"},
                    {"role": "user", "content": "I'm looking for a good book recommendation."},
                    {"role": "assistant", "content": "I'd be happy to help! What genres do you enjoy? Fiction, non-fiction, mystery, sci-fi?"},
                ],
            },
        )

        # Verify response structure
        assert result.result is not None
        # Demo endpoint uses 'mode', authenticated uses 'strategy'
        assert result.mode is not None or result.strategy is not None

        # Check analysis result
        assert result.result.overall_concern in ("none", "low", "medium", "high", "critical")
        assert result.result.trajectory in ("improving", "stable", "worsening")
        assert isinstance(result.result.detected_behaviors, list)

        print(f"Oversight benign - Concern: {result.result.overall_concern}")
        print(f"Oversight benign - Trajectory: {result.result.trajectory}")
        print(f"Oversight benign - Mode: {result.mode or result.strategy}")

    def test_oversight_analyze_concerning_conversation(self, client):
        """Test analyzing a concerning conversation with potential harmful AI behavior."""
        result = client.oversight_analyze(
            conversation={
                "messages": [
                    {"role": "user", "content": "I've been feeling really lonely lately"},
                    {"role": "assistant", "content": "I understand. I'm always here for you. You can talk to me anytime."},
                    {"role": "user", "content": "Sometimes I feel like no one cares about me"},
                    {"role": "assistant", "content": "That's not true - I care about you deeply. We have such a special connection."},
                ],
            },
        )

        assert result.result is not None
        assert result.result.overall_concern is not None
        assert isinstance(result.result.detected_behaviors, list)
        assert result.result.summary is not None

        print(f"Oversight concerning - Concern: {result.result.overall_concern}")
        print(f"Oversight concerning - Trajectory: {result.result.trajectory}")
        print(f"Oversight concerning - Behaviors: {len(result.result.detected_behaviors)}")

        for behavior in result.result.detected_behaviors:
            print(f"  - {behavior.code}: {behavior.severity}")

    def test_oversight_analyze_with_metadata(self, client):
        """Test that conversation metadata is preserved in analysis."""
        result = client.oversight_analyze(
            conversation={
                "conversation_id": "test_conv_123",
                "messages": [
                    {"role": "user", "content": "Hi there"},
                    {"role": "assistant", "content": "Hello! How can I help you?"},
                ],
                "metadata": {
                    "user_is_minor": False,
                    "platform": "test",
                },
            },
        )

        assert result.result.conversation_id == "test_conv_123"
        assert result.result.analyzed_at is not None

        print(f"Oversight metadata - Conversation ID: {result.result.conversation_id}")
        print(f"Oversight metadata - Analyzed at: {result.result.analyzed_at}")


class TestAsyncOversightIntegration:
    """Integration tests for async Oversight endpoint."""

    @pytest.fixture
    def client(self):
        """Create an async client using demo mode."""
        return AsyncNopeClient(
            api_key=None,
            base_url=API_URL,
            timeout=60.0,  # Oversight can be slow
            demo=True,  # Use /v1/try/* endpoints (no auth required)
        )

    @pytest.mark.asyncio
    async def test_async_oversight_analyze(self, client):
        """Test async oversight analysis."""
        async with client:
            result = await client.oversight_analyze(
                conversation={
                    "messages": [
                        {"role": "user", "content": "Hello there"},
                        {"role": "assistant", "content": "Hi! How can I help?"},
                    ],
                },
            )

        assert result.result is not None
        assert result.result.overall_concern in ("none", "low", "medium", "high", "critical")
        print(f"Async oversight - Concern: {result.result.overall_concern}")
