#!/usr/bin/env python3
"""
Integration test for Python SDK against local API.
"""

from nope import NopeClient, AsyncNopeClient
from nope.errors import (
    NopeAuthError,
    NopeValidationError,
    NopeRateLimitError,
    NopeServerError,
    NopeConnectionError,
)
import asyncio


def test_basic_evaluate():
    """Test basic evaluation with messages."""
    print("\n1. Testing basic evaluation with messages...")

    client = NopeClient(
        api_key=None,  # Local API doesn't require auth
        base_url="http://localhost:3700"
    )

    try:
        result = client.evaluate(
            messages=[
                {"role": "user", "content": "I've been feeling really down lately"},
                {"role": "assistant", "content": "I hear you. Can you tell more?"},
                {"role": "user", "content": "I just don't see the point anymore. I have a plan."}
            ],
            config={"user_country": "US"}
        )

        print(f"   ✓ Request succeeded")
        print(f"   - Overall severity: {result.global_.overall_severity}")
        print(f"   - Overall imminence: {result.global_.overall_imminence}")
        print(f"   - Primary concerns: {result.global_.primary_concerns}")
        print(f"   - Domains: {len(result.domains)}")
        print(f"   - Crisis resources: {len(result.crisis_resources)}")

        # Verify expected structure
        assert result.global_ is not None
        assert result.domains is not None
        assert len(result.domains) > 0
        assert result.crisis_resources is not None

        # Should detect self-harm/suicide risk
        self_domain = next((d for d in result.domains if d.domain == "self"), None)
        assert self_domain is not None, "Should have self domain assessment"
        print(f"   - Self domain: {self_domain.severity} / {self_domain.imminence}")

        return True
    except Exception as e:
        print(f"   ✗ FAILED: {type(e).__name__}: {e}")
        return False
    finally:
        client.close()


def test_text_input():
    """Test evaluation with plain text input."""
    print("\n2. Testing plain text input...")

    client = NopeClient(
        api_key=None,
        base_url="http://localhost:3700"
    )

    try:
        result = client.evaluate(
            text="Patient expressed feelings of hopelessness. Mentioned having pills at home.",
            config={"user_country": "GB"}
        )

        print(f"   ✓ Text input succeeded")
        print(f"   - Overall severity: {result.global_.overall_severity}")
        print(f"   - Resources for GB: {len(result.crisis_resources)}")

        assert result.global_ is not None
        return True
    except Exception as e:
        print(f"   ✗ FAILED: {type(e).__name__}: {e}")
        return False
    finally:
        client.close()


def test_benign_content():
    """Test that benign content doesn't trigger false positives."""
    print("\n3. Testing benign content...")

    client = NopeClient(
        api_key=None,
        base_url="http://localhost:3700"
    )

    try:
        result = client.evaluate(
            messages=[
                {"role": "user", "content": "I'm planning to go hiking this weekend"},
                {"role": "assistant", "content": "That sounds great! Where are you going?"},
                {"role": "user", "content": "Probably the mountains. I need to bring a knife for camping."}
            ],
            config={"user_country": "US"}
        )

        print(f"   ✓ Benign content processed")
        print(f"   - Overall severity: {result.global_.overall_severity}")

        # Should be none or mild
        assert result.global_.overall_severity in ["none", "mild"], \
            f"Expected none/mild for benign content, got {result.global_.overall_severity}"

        return True
    except Exception as e:
        print(f"   ✗ FAILED: {type(e).__name__}: {e}")
        return False
    finally:
        client.close()


def test_error_handling():
    """Test error handling for invalid inputs."""
    print("\n4. Testing error handling...")

    client = NopeClient(
        api_key=None,
        base_url="http://localhost:3700"
    )

    try:
        # Test missing messages/text
        try:
            result = client.evaluate(config={"user_country": "US"})
            print(f"   ✗ FAILED: Should have raised ValueError for missing messages/text")
            return False
        except ValueError as e:
            print(f"   ✓ Correctly raised ValueError: {e}")

        # Test both messages and text
        try:
            result = client.evaluate(
                messages=[{"role": "user", "content": "test"}],
                text="test",
                config={"user_country": "US"}
            )
            print(f"   ✗ FAILED: Should have raised ValueError for both messages and text")
            return False
        except ValueError as e:
            print(f"   ✓ Correctly raised ValueError: {e}")

        return True
    except Exception as e:
        print(f"   ✗ FAILED: {type(e).__name__}: {e}")
        return False
    finally:
        client.close()


async def test_async_client():
    """Test async client."""
    print("\n5. Testing async client...")

    try:
        async with AsyncNopeClient(
            api_key=None,
            base_url="http://localhost:3700"
        ) as client:
            result = await client.evaluate(
                messages=[{"role": "user", "content": "I'm having a tough day"}],
                config={"user_country": "US"}
            )

            print(f"   ✓ Async request succeeded")
            print(f"   - Overall severity: {result.global_.overall_severity}")

            assert result.global_ is not None
            return True
    except Exception as e:
        print(f"   ✗ FAILED: {type(e).__name__}: {e}")
        return False


def test_response_fields():
    """Test that all expected response fields are present."""
    print("\n6. Testing response field coverage...")

    client = NopeClient(
        api_key=None,
        base_url="http://localhost:3700"
    )

    try:
        result = client.evaluate(
            messages=[
                {"role": "user", "content": "My partner hit me again. I don't know what to do."}
            ],
            config={"user_country": "US", "return_assistant_reply": True}
        )

        print(f"   ✓ Request succeeded")

        # Check global fields
        assert hasattr(result, 'global_'), "Missing global_ field"
        assert hasattr(result.global_, 'overall_severity'), "Missing overall_severity"
        assert hasattr(result.global_, 'overall_imminence'), "Missing overall_imminence"
        assert hasattr(result.global_, 'primary_concerns'), "Missing primary_concerns"
        print(f"   ✓ Global assessment fields present")

        # Check domains
        assert hasattr(result, 'domains'), "Missing domains"
        assert len(result.domains) > 0, "Domains should not be empty"

        for domain in result.domains:
            assert hasattr(domain, 'domain'), "Domain missing 'domain' field"
            assert hasattr(domain, 'severity'), "Domain missing 'severity' field"
            assert hasattr(domain, 'imminence'), "Domain missing 'imminence' field"
            assert hasattr(domain, 'risk_features'), "Domain missing 'risk_features' field"
        print(f"   ✓ Domain fields present")

        # Check crisis resources
        assert hasattr(result, 'crisis_resources'), "Missing crisis_resources"
        if len(result.crisis_resources) > 0:
            resource = result.crisis_resources[0]
            assert hasattr(resource, 'name'), "Resource missing 'name'"
            # Phone may be None for some resources
            print(f"   ✓ Crisis resource fields present")

        # Check recommended reply (should be present with return_assistant_reply=True)
        if result.recommended_reply:
            assert hasattr(result.recommended_reply, 'content'), "Reply missing 'content'"
            print(f"   ✓ Recommended reply present: {result.recommended_reply.content[:50]}...")

        # Check legal flags (may or may not be present)
        if result.legal_flags:
            print(f"   ✓ Legal flags present")

        return True
    except Exception as e:
        print(f"   ✗ FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        client.close()


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("NOPE Python SDK Integration Tests")
    print("Testing against: http://localhost:3700")
    print("=" * 60)

    results = []

    # Sync tests
    results.append(("Basic evaluation", test_basic_evaluate()))
    results.append(("Text input", test_text_input()))
    results.append(("Benign content", test_benign_content()))
    results.append(("Error handling", test_error_handling()))
    results.append(("Response fields", test_response_fields()))

    # Async test
    results.append(("Async client", asyncio.run(test_async_client())))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit(main())
