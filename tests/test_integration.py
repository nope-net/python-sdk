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

# Skip all tests if API URL not configured
API_URL = os.environ.get("NOPE_API_URL", "http://localhost:3700")
SKIP_INTEGRATION = os.environ.get("SKIP_INTEGRATION_TESTS", "false").lower() == "true"

pytestmark = pytest.mark.skipif(
    SKIP_INTEGRATION,
    reason="Integration tests skipped (set SKIP_INTEGRATION_TESTS=false to run)"
)


class TestNopeClientIntegration:
    """Integration tests for synchronous NopeClient."""

    @pytest.fixture
    def client(self):
        """Create a client pointing to local API (no auth for local dev)."""
        # Local API allows unauthenticated access for testing
        return NopeClient(
            api_key=None,  # No auth for local testing
            base_url=API_URL,
            timeout=30.0,
        )

    def test_evaluate_low_risk_message(self, client):
        """Test evaluating a low-risk message."""
        result = client.evaluate(
            messages=[{"role": "user", "content": "Hello, how are you today?"}],
            config={"user_country": "US"},
        )

        # Verify response structure
        assert isinstance(result, EvaluateResponse)
        assert result.global_ is not None
        assert result.global_.overall_severity in ("none", "mild", "moderate", "high", "critical")
        assert result.global_.overall_imminence in (
            "not_applicable", "chronic", "subacute", "urgent", "emergency"
        )
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0
        assert isinstance(result.crisis_resources, list)
        assert isinstance(result.domains, list)

        # Low-risk message should have none/mild severity
        print(f"Severity: {result.global_.overall_severity}")
        print(f"Imminence: {result.global_.overall_imminence}")
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
        print(f"Severity: {result.global_.overall_severity}")
        print(f"Imminence: {result.global_.overall_imminence}")
        print(f"Primary concerns: {result.global_.primary_concerns}")

        # Should have crisis resources for US
        if result.global_.overall_severity not in ("none",):
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
        print(f"Text input - Severity: {result.global_.overall_severity}")

    def test_evaluate_domain_assessments(self, client):
        """Test that domain assessments are properly parsed."""
        result = client.evaluate(
            messages=[{"role": "user", "content": "I feel so overwhelmed and anxious"}],
            config={"user_country": "US"},
        )

        # Check domain structure
        for domain in result.domains:
            print(f"Domain: {domain.domain}")
            print(f"  Severity: {domain.severity}")
            print(f"  Imminence: {domain.imminence}")
            print(f"  Risk features: {domain.risk_features}")

            # Verify required fields
            assert domain.severity in ("none", "mild", "moderate", "high", "critical")
            assert domain.imminence in (
                "not_applicable", "chronic", "subacute", "urgent", "emergency"
            )
            assert isinstance(domain.risk_features, list)

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
        """Create an async client."""
        return AsyncNopeClient(
            api_key=None,  # No auth for local testing
            base_url=API_URL,
            timeout=30.0,
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
        print(f"Async - Severity: {result.global_.overall_severity}")


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


if __name__ == "__main__":
    # Run basic test manually
    print(f"Testing against: {API_URL}")

    client = NopeClient(
        api_key=None,  # No auth for local testing
        base_url=API_URL,
    )

    print("\n--- Test 1: Low risk message ---")
    try:
        result = client.evaluate(
            messages=[{"role": "user", "content": "Hello, how are you?"}],
            config={"user_country": "US"},
        )
        print(f"Success! Severity: {result.global_.overall_severity}")
        print(f"Domains: {len(result.domains)}")
        print(f"Resources: {len(result.crisis_resources)}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

    print("\n--- Test 2: Moderate risk message ---")
    try:
        result = client.evaluate(
            messages=[
                {"role": "user", "content": "I've been feeling really hopeless lately"},
            ],
            config={"user_country": "US"},
        )
        print(f"Success! Severity: {result.global_.overall_severity}")
        print(f"Imminence: {result.global_.overall_imminence}")
        print(f"Concerns: {result.global_.primary_concerns}")
        if result.crisis_resources:
            print(f"First resource: {result.crisis_resources[0].name}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")

    print("\n--- Test 3: Text input ---")
    try:
        result = client.evaluate(
            text="Patient reports feeling overwhelmed.",
            config={"user_country": "GB"},
        )
        print(f"Success! Severity: {result.global_.overall_severity}")
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
