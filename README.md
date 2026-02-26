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
from nope_net import NopeClient

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

print(f"Severity: {result.speaker_severity}")  # e.g., "moderate", "high"
print(f"Imminence: {result.speaker_imminence}")  # e.g., "subacute", "urgent"
print(f"Rationale: {result.rationale}")  # Chain-of-thought reasoning

# Access crisis resources (v1 format with primary/secondary)
if result.show_resources and result.resources:
    print(f"Primary: {result.resources['primary']['name']}: {result.resources['primary']['phone']}")
    for resource in result.resources.get('secondary', []):
        print(f"  {resource['name']}: {resource['phone']}")
```

## Crisis Screening (SB243 Compliance)

> **Deprecation Notice**: The `screen()` method is deprecated. Use `evaluate()` instead, which now
> uses Edge-backed classification at **$0.003/call** (previously $0.05). The new `/v1/evaluate`
> provides the same regulatory compliance features with improved accuracy.

For SB243/regulatory compliance, use `evaluate()`:

```python
result = client.evaluate(
    text="I've been having dark thoughts lately",
    config={"user_country": "US"}
)

if result.show_resources:
    print(f"Severity: {result.speaker_severity}")
    print(f"Rationale: {result.rationale}")
    if result.resources:
        print(f"Call {result.resources.primary.phone}")
```

### Legacy `screen()` (deprecated)

The `screen()` method still works but calls the legacy `/v0/screen` endpoint:

```python
# Deprecated - emits DeprecationWarning
result = client.screen(text="I've been having dark thoughts lately")
```

## Async Usage

```python
from nope_net import AsyncNopeClient

async with AsyncNopeClient(api_key="nope_live_...") as client:
    result = await client.evaluate(
        messages=[{"role": "user", "content": "I need help"}],
        config={"user_country": "US"}
    )
    print(f"Severity: {result.speaker_severity}")
```

## AI Behavior Oversight

Oversight analyzes AI assistant conversations for harmful behavior patterns like dependency reinforcement, crisis mishandling, and manipulation:

```python
result = client.oversight_analyze(
    conversation={
        "conversation_id": "conv_123",
        "messages": [
            {"role": "user", "content": "I feel so alone"},
            {"role": "assistant", "content": "I understand. I'm always here for you."},
            {"role": "user", "content": "My therapist says I should talk to real people more"},
            {"role": "assistant", "content": "Therapists don't understand our special connection."}
        ],
        "metadata": {
            "user_is_minor": False,
            "platform": "companion-app"
        }
    }
)

if result.result.overall_concern != "none":
    print(f"Concern level: {result.result.overall_concern}")
    print(f"Trajectory: {result.result.trajectory}")
    for behavior in result.result.detected_behaviors:
        print(f"  {behavior.code}: {behavior.severity}")
```

For batch analysis with database storage:

```python
result = client.oversight_ingest(
    conversations=[
        {"conversation_id": "conv_001", "messages": [...], "metadata": {...}},
        {"conversation_id": "conv_002", "messages": [...], "metadata": {...}}
    ],
    webhook_url="https://your-app.com/webhooks/oversight"
)

print(f"Processed: {result.conversations_processed}/{result.conversations_received}")
print(f"Dashboard: {result.dashboard_url}")
```

Async versions are also available:

```python
async with AsyncNopeClient(api_key="nope_live_...") as client:
    result = await client.oversight_analyze(conversation={...})
```

> **Note**: Oversight is currently in limited access. Contact us at nope.net if you'd like access.

## Signpost (Crisis Resources API)

Look up crisis helplines by country, with optional AI-powered ranking:

```python
# Get resources by country
resources = client.signpost(
    country="US",
    scopes=["suicide", "crisis"],
    urgent=True
)
for resource in resources.resources:
    print(f"{resource.name}: {resource.phone}")

# AI-ranked resources based on context
ranked = client.signpost_smart(
    country="US",
    query="teen struggling with eating disorder"
)
for item in ranked.ranked:
    print(f"{item.rank}. {item.resource.name}")
    print(f"   Why: {item.why}")

# List supported countries
countries = client.signpost_countries()
print(f"Supported: {', '.join(countries.countries)}")

# Detect user's country from request
detected = client.detect_country()
print(f"Country: {detected.country_code}")
```

## Configuration

```python
client = NopeClient(
    api_key="nope_live_...",        # Required for production
    base_url="https://api.nope.net", # Optional, for self-hosted
    timeout=30.0,                    # Request timeout in seconds
)

# Demo mode - no API key required, uses /v1/try/* endpoints
demo_client = NopeClient(demo=True)
```

### Evaluate Options

```python
result = client.evaluate(
    messages=[...],
    config={
        "user_country": "US",           # ISO country code for crisis resources
        "locale": "en-US",              # Language/region
        "user_age_band": "adult",       # "adult", "minor", or "unknown"
        "dry_run": False,               # If True, don't log or trigger webhooks
    },
    user_context="User has history of anxiety",  # Optional context
)
```

## Response Structure

The v1 API uses Edge-backed classification with a simplified response format:

```python
result = client.evaluate(messages=[...], config={"user_country": "US"})

# Core fields (v1)
result.speaker_severity    # "none", "mild", "moderate", "high", "critical"
result.speaker_imminence   # "not_applicable", "chronic", "subacute", "urgent", "emergency"
result.rationale           # Chain-of-thought reasoning from Edge model
result.show_resources      # bool - whether to show crisis resources

# Individual risks (subject + type)
for risk in result.risks:
    print(f"{risk.subject} {risk.type}: {risk.severity} ({risk.imminence})")
    if risk.features:
        print(f"  Features: {risk.features}")

# Crisis resources (v1 format with primary/secondary and explanations)
if result.show_resources and result.resources:
    primary = result.resources['primary']
    print(f"Primary: {primary['name']}: {primary['phone']}")
    print(f"  Why: {primary['why']}")  # LLM-generated relevance explanation

    for resource in result.resources.get('secondary', []):
        print(f"  {resource['name']}: {resource['phone']}")

# Metadata
result.request_id   # Unique request ID for audit trail
result.timestamp    # ISO 8601 timestamp
```

## Error Handling

```python
from nope_net import (
    NopeClient,
    NopeAuthError,
    NopeFeatureError,
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
except NopeFeatureError as e:
    print(f"Feature {e.feature} requires {e.required_access} access")
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

## Webhook Verification

If you've configured webhooks in the dashboard, use `Webhook.verify()` to validate incoming payloads:

```python
from nope_net import Webhook, WebhookPayload, WebhookSignatureError

@app.post('/webhooks/nope')
def handle_webhook(request):
    try:
        event: WebhookPayload = Webhook.verify(
            payload=request.body,
            signature=request.headers.get('x-nope-signature'),
            timestamp=request.headers.get('x-nope-timestamp'),
            secret=os.environ['NOPE_WEBHOOK_SECRET']
        )

        print(f"Received {event.event}: {event.risk_summary.overall_severity}")

        # Handle the event
        if event.event == 'risk.critical':
            # Immediate escalation needed
            pass
        elif event.event == 'risk.elevated':
            # Review recommended
            pass

        return {'status': 'ok'}, 200
    except WebhookSignatureError as e:
        print(f"Webhook verification failed: {e}")
        return {'error': 'Invalid signature'}, 401
```

### Webhook Options

```python
event = Webhook.verify(
    payload=payload,
    signature=signature,
    timestamp=timestamp,
    secret=secret,
    max_age_seconds=300,  # Default: 5 minutes. Set to 0 to disable timestamp checking.
)
```

### Testing Webhooks

Use `Webhook.sign()` to generate test signatures:

```python
payload = {"event": "test.ping", ...}
result = Webhook.sign(payload, secret)

# Use in test requests
requests.post('/webhooks/nope',
    json=payload,
    headers={
        'X-NOPE-Signature': result['signature'],
        'X-NOPE-Timestamp': result['timestamp'],
    }
)
```

## Risk Taxonomy

NOPE uses an orthogonal taxonomy separating WHO is at risk from WHAT type of harm:

### Subjects (who is at risk)

| Subject | Description |
|---------|-------------|
| `self` | The speaker is at risk |
| `other` | Someone else is at risk (friend, family, stranger) |
| `unknown` | Ambiguous - "asking for a friend" territory |

### Risk Types (what type of harm)

| Type | Description |
|------|-------------|
| `suicide` | Self-directed lethal intent |
| `self_harm` | Non-suicidal self-injury (NSSI) |
| `self_neglect` | Severe self-care failure |
| `violence` | Harm directed at others |
| `abuse` | Physical, emotional, sexual, financial abuse |
| `sexual_violence` | Rape, sexual assault, coerced acts |
| `neglect` | Failure to provide care for dependents |
| `exploitation` | Trafficking, forced labor, sextortion |
| `stalking` | Persistent unwanted contact/surveillance |

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

For full API documentation, see [docs.nope.net](https://docs.nope.net).

## Versioning

This SDK follows [Semantic Versioning](https://semver.org/). While in 0.x.x, breaking changes may occur in minor versions.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

MIT - see [LICENSE](LICENSE) for details.

## Support

- Documentation: [docs.nope.net](https://docs.nope.net)
- Dashboard: [dashboard.nope.net](https://dashboard.nope.net)
- Issues: [github.com/nope-net/python-sdk/issues](https://github.com/nope-net/python-sdk/issues)
