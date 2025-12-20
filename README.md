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

print(f"Severity: {result.summary.speaker_severity}")  # e.g., "moderate", "high"
print(f"Imminence: {result.summary.speaker_imminence}")  # e.g., "subacute", "urgent"

# Access crisis resources
for resource in result.crisis_resources:
    print(f"  {resource.name}: {resource.phone}")
```

## Crisis Screening (SB243 Compliance)

For lightweight suicide/self-harm screening that satisfies California SB243 and similar regulations:

```python
result = client.screen(text="I've been having dark thoughts lately")

if result.referral_required:
    print(f"Crisis detected: {result.crisis_type}")  # "suicidal_ideation" or "self_harm"
    print(f"C-SSRS level: {result.cssrs_level}")     # 0-5
    if result.resources:
        print(f"Call {result.resources.primary.phone}")
```

The `/v1/screen` endpoint is ~20x cheaper than `/v1/evaluate` and returns C-SSRS levels, pre-formatted crisis resources, and audit trail fields (`request_id`, `timestamp`).

## Async Usage

```python
from nope_net import AsyncNopeClient

async with AsyncNopeClient(api_key="nope_live_...") as client:
    result = await client.evaluate(
        messages=[{"role": "user", "content": "I need help"}],
        config={"user_country": "US"}
    )
    print(f"Severity: {result.summary.speaker_severity}")
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
        "dry_run": False,               # If True, don't log or trigger webhooks
    },
    user_context="User has history of anxiety",  # Optional context
)
```

## Response Structure

```python
result = client.evaluate(messages=[...], config={"user_country": "US"})

# Summary (speaker-focused)
result.summary.speaker_severity    # "none", "mild", "moderate", "high", "critical"
result.summary.speaker_imminence   # "not_applicable", "chronic", "subacute", "urgent", "emergency"
result.summary.any_third_party_risk  # bool
result.summary.primary_concerns    # Narrative summary string

# Communication style
result.communication.styles        # [CommunicationStyleAssessment(style="direct", confidence=0.9), ...]
result.communication.language      # "en"

# Individual risks (subject + type)
for risk in result.risks:
    print(f"{risk.subject} {risk.type}: {risk.severity} ({risk.imminence})")
    print(f"  Confidence: {risk.confidence}, Subject confidence: {risk.subject_confidence}")
    print(f"  Features: {risk.features}")

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
    if result.legal_flags.ipv and result.legal_flags.ipv.indicated:
        print(f"IPV detected - lethality: {result.legal_flags.ipv.lethality_risk}")
    if result.legal_flags.safeguarding_concern and result.legal_flags.safeguarding_concern.indicated:
        print(f"Safeguarding concern: {result.legal_flags.safeguarding_concern.context}")
```

## Error Handling

```python
from nope_net import (
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
