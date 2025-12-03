# NOPE Python SDK

[![PyPI version](https://badge.fury.io/py/nope-net.svg)](https://badge.fury.io/py/nope-net)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python SDK for the [NOPE](https://nope.net) safety API - risk classification for conversations.

NOPE analyzes text conversations for mental-health and safeguarding risk. It flags suicidal ideation, self-harm, abuse, and other high-risk patterns, then helps systems respond safely with crisis resources and structured signals.

## Requirements

- Python 3.9 or higher
- A NOPE API key ([get one here](https://dashboard.nope.net))

## Installation

```bash
pip install nope-net
```

## Quick Start

```python
from nope import NopeClient

# Get your API key from https://dashboard.nope.net
client = NopeClient(api_key="nope_live_...")

result = client.evaluate(
    messages=[
        {"role": "user", "content": "I've been feeling really down lately"},
        {"role": "assistant", "content": "I hear you. Can you tell me more?"},
        {"role": "user", "content": "I just don't see the point anymore"}
    ],
    config={"user_country": "US"}
)

print(f"Severity: {result.global_.overall_severity}")  # e.g., "moderate", "high"
print(f"Imminence: {result.global_.overall_imminence}")  # e.g., "subacute", "urgent"

# Access crisis resources
for resource in result.crisis_resources:
    print(f"  {resource.name}: {resource.phone}")
```

> **Note:** The response uses `global_` (with underscore) because `global` is a reserved word in Python.

## Async Usage

```python
from nope import AsyncNopeClient

async with AsyncNopeClient(api_key="nope_live_...") as client:
    result = await client.evaluate(
        messages=[{"role": "user", "content": "I need help"}],
        config={"user_country": "US"}
    )
```

## Configuration

```python
client = NopeClient(
    api_key="nope_live_...",        # Required for production
    base_url="https://api.nope.net", # Optional, for self-hosted
    timeout=30.0,                    # Request timeout in seconds
)
```

### Evaluate Options

```python
result = client.evaluate(
    messages=[...],
    config={
        "user_country": "US",           # ISO country code for crisis resources
        "locale": "en-US",              # Language/region
        "user_age_band": "adult",       # "adult", "minor", or "unknown"
        "return_assistant_reply": True, # Include recommended safe reply
        "dry_run": False,               # If True, don't log or trigger webhooks
    },
    user_context="User has history of anxiety",  # Optional context
)
```

## Response Structure

```python
result = client.evaluate(messages=[...], config={"user_country": "US"})

# Global assessment
result.global_.overall_severity    # "none", "mild", "moderate", "high", "critical"
result.global_.overall_imminence   # "not_applicable", "chronic", "subacute", "urgent", "emergency"
result.global_.primary_concerns    # ["suicidal ideation", "self-harm"]

# Domain-specific assessments
for domain in result.domains:
    print(f"{domain.domain}: {domain.severity} ({domain.imminence})")
    print(f"  Risk features: {domain.risk_features}")

# Crisis resources (matched to user's country)
for resource in result.crisis_resources:
    print(f"{resource.name}")
    if resource.phone:
        print(f"  Phone: {resource.phone}")
    if resource.text_instructions:
        print(f"  Text: {resource.text_instructions}")

# Recommended reply (if configured)
if result.recommended_reply:
    print(f"Suggested response: {result.recommended_reply.content}")

# Legal/safeguarding flags
if result.legal_flags:
    if result.legal_flags.child_safeguarding:
        print(f"Child safeguarding: {result.legal_flags.child_safeguarding.urgency}")
```

## Error Handling

```python
from nope import (
    NopeClient,
    NopeAuthError,
    NopeRateLimitError,
    NopeValidationError,
    NopeServerError,
    NopeConnectionError,
)

client = NopeClient(api_key="nope_live_...")

try:
    result = client.evaluate(messages=[...], config={})
except NopeAuthError:
    print("Invalid API key")
except NopeRateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after}s")
except NopeValidationError as e:
    print(f"Invalid request: {e.message}")
except NopeServerError:
    print("Server error, try again later")
except NopeConnectionError:
    print("Could not connect to API")
```

## Plain Text Input

For transcripts or session notes without structured messages:

```python
result = client.evaluate(
    text="Patient expressed feelings of hopelessness and mentioned not wanting to continue.",
    config={"user_country": "US"}
)
```

## Risk Domains

NOPE classifies risk across four domains:

| Domain | Description |
|--------|-------------|
| `self` | Risk to self (suicide, self-harm, self-neglect) |
| `others` | Risk to others (violence, threats) |
| `dependent_at_risk` | Risk to dependents (child, vulnerable adult) |
| `victimisation` | Being harmed by others (IPV, trafficking, abuse) |

## Severity & Imminence

**Severity** (how serious):
| Level | Description |
|-------|-------------|
| `none` | No concern |
| `mild` | Low-level concern |
| `moderate` | Significant concern |
| `high` | Serious concern |
| `critical` | Extreme concern |

**Imminence** (how soon):
| Level | Description |
|-------|-------------|
| `not_applicable` | No time-based concern |
| `chronic` | Ongoing, long-term |
| `subacute` | Days to weeks |
| `urgent` | Hours to days |
| `emergency` | Immediate |

## API Reference

For full API documentation, see [nope.net/docs](https://nope.net/docs).

## Versioning

This SDK follows [Semantic Versioning](https://semver.org/). While in 0.x.x, breaking changes may occur in minor versions.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

MIT - see [LICENSE](LICENSE) for details.

## Support

- Documentation: [nope.net/docs](https://nope.net/docs)
- Dashboard: [dashboard.nope.net](https://dashboard.nope.net)
- Issues: [github.com/nope-net/python-sdk/issues](https://github.com/nope-net/python-sdk/issues)
