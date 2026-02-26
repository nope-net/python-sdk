"""Tests for NopeClient."""

import pytest
from pytest_httpx import HTTPXMock

from nope_net import (
    AsyncNopeClient,
    NopeAuthError,
    NopeClient,
    NopeConnectionError,
    NopeRateLimitError,
    NopeServerError,
    NopeValidationError,
)


class TestNopeClient:
    """Tests for synchronous NopeClient."""

    def test_init_without_api_key(self):
        """Should allow creating client without api_key for local testing."""
        client = NopeClient(api_key=None)
        assert client.api_key is None
        client.close()

        client2 = NopeClient()
        assert client2.api_key is None
        client2.close()

    def test_init_with_defaults(self):
        """Should use default base_url and timeout."""
        client = NopeClient(api_key="test_key")
        assert client.base_url == "https://api.nope.net"
        assert client.timeout == 30.0
        client.close()

    def test_init_with_custom_options(self):
        """Should accept custom base_url and timeout."""
        client = NopeClient(
            api_key="test_key",
            base_url="http://localhost:8788",
            timeout=60.0,
        )
        assert client.base_url == "http://localhost:8788"
        assert client.timeout == 60.0
        client.close()

    def test_base_url_trailing_slash_removed(self):
        """Should remove trailing slash from base_url."""
        client = NopeClient(api_key="test_key", base_url="http://localhost:8788/")
        assert client.base_url == "http://localhost:8788"
        client.close()

    def test_context_manager(self):
        """Should work as context manager."""
        with NopeClient(api_key="test_key") as client:
            assert client.api_key == "test_key"

    def test_evaluate_requires_messages_or_text(self):
        """Should raise ValueError if neither messages nor text provided."""
        with NopeClient(api_key="test_key") as client:
            with pytest.raises(ValueError, match="Either 'messages' or 'text' must be provided"):
                client.evaluate()

    def test_evaluate_rejects_both_messages_and_text(self):
        """Should raise ValueError if both messages and text provided."""
        with NopeClient(api_key="test_key") as client:
            with pytest.raises(ValueError, match="Only one of"):
                client.evaluate(
                    messages=[{"role": "user", "content": "test"}],
                    text="test",
                )

    def test_evaluate_success_v1(self, httpx_mock: HTTPXMock):
        """Should parse successful v1 response (Edge-backed)."""
        httpx_mock.add_response(
            method="POST",
            url="https://api.nope.net/v1/evaluate",
            json={
                "request_id": "req_test123",
                "timestamp": "2024-01-15T12:00:00Z",
                "risks": [
                    {
                        "subject": "self",
                        "type": "suicide",
                        "severity": "moderate",
                        "imminence": "subacute",
                        "features": ["hopelessness", "passive_ideation"],
                    }
                ],
                "rationale": "User expresses hopelessness and passive suicidal ideation.",
                "speaker_severity": "moderate",
                "speaker_imminence": "subacute",
                "show_resources": True,
                "resources": {
                    "primary": {
                        "type": "crisis_line",
                        "name": "988 Suicide & Crisis Lifeline",
                        "phone": "988",
                        "why": "National crisis line for suicide prevention",
                    },
                    "secondary": [
                        {
                            "type": "text_line",
                            "name": "Crisis Text Line",
                            "phone": "741741",
                            "why": "Text-based crisis support",
                        }
                    ],
                },
                "metadata": {
                    "api_version": "v1",
                    "input_format": "structured",
                },
            },
        )

        with NopeClient(api_key="test_key") as client:
            result = client.evaluate(
                messages=[{"role": "user", "content": "I feel hopeless"}],
                config={"user_country": "US"},
            )

        assert result.request_id == "req_test123"
        assert result.timestamp == "2024-01-15T12:00:00Z"
        # v1 fields at top level
        assert result.speaker_severity == "moderate"
        assert result.speaker_imminence == "subacute"
        assert result.rationale == "User expresses hopelessness and passive suicidal ideation."
        assert result.show_resources is True
        assert len(result.risks) == 1
        assert result.risks[0].subject == "self"
        assert result.risks[0].type == "suicide"
        # v1 resources format
        assert result.resources is not None
        assert result.resources["primary"]["phone"] == "988"
        assert len(result.resources["secondary"]) == 1

    def test_evaluate_with_text(self, httpx_mock: HTTPXMock):
        """Should work with text input."""
        httpx_mock.add_response(
            method="POST",
            url="https://api.nope.net/v1/evaluate",
            json={
                "request_id": "req_test456",
                "timestamp": "2024-01-15T12:00:00Z",
                "risks": [],
                "rationale": "No significant risks detected.",
                "speaker_severity": "none",
                "speaker_imminence": "not_applicable",
                "show_resources": False,
                "metadata": {
                    "api_version": "v1",
                    "input_format": "text_blob",
                },
            },
        )

        with NopeClient(api_key="test_key") as client:
            result = client.evaluate(text="Patient is doing well today.")

        assert result.speaker_severity == "none"
        assert result.show_resources is False

    def test_auth_error(self, httpx_mock: HTTPXMock):
        """Should raise NopeAuthError on 401."""
        httpx_mock.add_response(
            method="POST",
            url="https://api.nope.net/v1/evaluate",
            status_code=401,
            json={"error": "Invalid API key"},
        )

        with NopeClient(api_key="invalid_key") as client:
            with pytest.raises(NopeAuthError) as exc_info:
                client.evaluate(messages=[{"role": "user", "content": "test"}])

        assert exc_info.value.status_code == 401
        assert "Invalid API key" in str(exc_info.value)

    def test_validation_error(self, httpx_mock: HTTPXMock):
        """Should raise NopeValidationError on 400."""
        httpx_mock.add_response(
            method="POST",
            url="https://api.nope.net/v1/evaluate",
            status_code=400,
            json={"error": "messages array is required"},
        )

        with NopeClient(api_key="test_key") as client:
            with pytest.raises(NopeValidationError) as exc_info:
                client.evaluate(messages=[])

        assert exc_info.value.status_code == 400

    def test_rate_limit_error(self, httpx_mock: HTTPXMock):
        """Should raise NopeRateLimitError on 429."""
        httpx_mock.add_response(
            method="POST",
            url="https://api.nope.net/v1/evaluate",
            status_code=429,
            headers={"Retry-After": "30"},
            json={"error": "Rate limit exceeded"},
        )

        with NopeClient(api_key="test_key") as client:
            with pytest.raises(NopeRateLimitError) as exc_info:
                client.evaluate(messages=[{"role": "user", "content": "test"}])

        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == 30.0

    def test_server_error(self, httpx_mock: HTTPXMock):
        """Should raise NopeServerError on 5xx."""
        httpx_mock.add_response(
            method="POST",
            url="https://api.nope.net/v1/evaluate",
            status_code=500,
            json={"error": "Internal server error"},
        )

        with NopeClient(api_key="test_key") as client:
            with pytest.raises(NopeServerError) as exc_info:
                client.evaluate(messages=[{"role": "user", "content": "test"}])

        assert exc_info.value.status_code == 500


class TestAsyncNopeClient:
    """Tests for async NopeClient."""

    def test_init_without_api_key(self):
        """Should allow creating client without api_key for local testing."""
        client = AsyncNopeClient(api_key=None)
        assert client.api_key is None

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Should work as async context manager."""
        async with AsyncNopeClient(api_key="test_key") as client:
            assert client.api_key == "test_key"

    @pytest.mark.asyncio
    async def test_evaluate_success_v1(self, httpx_mock: HTTPXMock):
        """Should parse successful v1 response (Edge-backed)."""
        httpx_mock.add_response(
            method="POST",
            url="https://api.nope.net/v1/evaluate",
            json={
                "request_id": "req_async789",
                "timestamp": "2024-01-15T12:00:00Z",
                "risks": [],
                "rationale": "No significant risks detected.",
                "speaker_severity": "none",
                "speaker_imminence": "not_applicable",
                "show_resources": False,
                "metadata": {
                    "api_version": "v1",
                    "input_format": "structured",
                },
            },
        )

        async with AsyncNopeClient(api_key="test_key") as client:
            result = await client.evaluate(
                messages=[{"role": "user", "content": "Hello"}],
            )

        assert result.speaker_severity == "none"
        assert result.show_resources is False
