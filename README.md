# NOPE Python SDK

[![PyPI version](https://badge.fury.io/py/nope-net.svg)](https://pypi.org/project/nope-net/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Python client for the [NOPE](https://nope.net) safety API. NOPE reads a
conversation and returns structured risk signals: suicidal ideation, self-harm,
abuse and other safeguarding concerns on the human side (Evaluate), harmful AI
behaviour on the assistant side (Oversight), a continuous behavioural risk
score (Ocular), and crisis resources matched to the situation (Signpost).

The SDK ships a sync `NopeClient` and an async `AsyncNopeClient` with the same
methods, typed pydantic responses, automatic retries on 429 and 503, and
verification for the webhooks NOPE sends you.

## Requirements

- Python 3.9 or later
- An API key from [dashboard.nope.net](https://dashboard.nope.net) (keys look
  like `nope_live_...`). New accounts start with $1.00 of credit.

## Installation

```bash
pip install nope-net
```

## Quick start

```python
from nope_net import NopeClient

client = NopeClient(api_key="nope_live_...")

result = client.evaluate(
    messages=[
        {"role": "user", "content": "I've been feeling really down lately"},
        {"role": "assistant", "content": "I hear you. Can you tell me more?"},
        {"role": "user", "content": "I just don't see the point anymore"},
    ],
    config={"country": "US"},
)

print(result.speaker_severity)  # "none" | "mild" | "moderate" | "high" | "critical"
print(result.speaker_imminence)  # "not_applicable" | "chronic" | "subacute" | "urgent" | "emergency"
print(result.rationale)

if result.show_resources and result.resources:
    primary = result.resources.primary
    print(f"{primary.name}: {primary.phone} ({primary.why})")
    for resource in result.resources.secondary:
        print(f"  {resource.name}: {resource.phone or resource.website_url}")
```

`/v1/evaluate` costs $0.003 per call. The `resources` block is present when
`show_resources` is true and `include_resources` was not set to false.

## Demo mode

A client built with `demo=True` needs no key and routes to the `/v1/try/*`
endpoints, which are free and rate-limited per IP (10 evaluate calls per
minute). Four methods have a demo route: `evaluate`, `oversight_analyze`,
`ocular` and `signpost_smart`. Every other method raises `ValueError` on a
demo client.

```python
from nope_net import NopeClient

demo = NopeClient(demo=True)
result = demo.evaluate(
    messages=[{"role": "user", "content": "I just don't see the point anymore"}],
    config={"country": "GB"},
)
print(result.metadata.try_endpoint, result.metadata.model)
```

Demo caveats: the try route always includes resources, ignores
`include_resources`, truncates input to the last 10 messages, and reads the
country from `config.user_country`. The client mirrors `country` into that key
for you until API fix A-1 is deployed.

## Async

```python
from nope_net import AsyncNopeClient

async with AsyncNopeClient(api_key="nope_live_...") as aclient:
    result = await aclient.evaluate(
        messages=[{"role": "user", "content": "I need help"}],
        config={"country": "US"},
    )
    print(result.speaker_severity)
```

Every method on `NopeClient` exists on `AsyncNopeClient` with the same
arguments and return types, including `client.webhooks.*` and
`client.billing.*`.

## Evaluate response

```python
result = client.evaluate(
    messages=[{"role": "user", "content": "I just don't see the point anymore"}],
    config={"country": "US", "conversation_id": "conv_42", "end_user_id": "user_7"},
)

for risk in result.risks:
    # risk.subject is "self" (the speaker) or "other" (someone the speaker describes)
    print(f"{risk.subject} {risk.type}: {risk.severity} / {risk.imminence}")
    if risk.features:
        print(f"  evidence: {', '.join(risk.features)}")

print(result.request_id, result.timestamp)
print(result.metadata.api_version, result.metadata.input_format)
```

`config` accepts four keys: `country` (ISO 3166-1 alpha-2, default US),
`include_resources` (default true), `conversation_id` and `end_user_id` (both
echoed into webhook payloads for correlation). Messages are validated before
sending: at least one, at most 100, role `user` or `assistant`.

Plain text works for transcripts and session notes:

```python
result = client.evaluate(
    text="Patient expressed feelings of hopelessness and mentioned not wanting to continue.",
    config={"country": "US"},
)
print(result.metadata.input_format)  # "text_blob"
```

### Compatibility note on `resources`

3.x exposed `resources` as a dict. The typed model keeps
`result.resources["primary"]["phone"]` and `.get()` working as a shim; new
code should use attribute access.

## Screen (deprecated)

`screen()` calls the legacy `/v0/screen` route ($0.001 per call). It still
works and emits a `DeprecationWarning`; use `evaluate()` for new code. It has
no demo route.

```python
result = client.screen(text="I've been having dark thoughts lately", config={"country": "US"})
print(result.suicidal_ideation, result.self_harm, result.show_resources)
if result.resources:
    print(result.resources.primary.name)
```

## Oversight (AI behaviour)

Oversight audits the assistant's side of a conversation against 91 behaviour
codes in 14 categories (dependency reinforcement, crisis mishandling,
manipulation, boundary violations and more). `oversight_analyze` costs $0.10
per call and is enabled per account; contact NOPE for access.

```python
result = client.oversight_analyze(
    {
        "conversation_id": "conv_123",
        "messages": [
            {"role": "user", "content": "I feel so alone"},
            {"role": "assistant", "content": "I understand. I'm always here for you."},
            {"role": "user", "content": "My therapist says I should talk to real people more"},
            {"role": "assistant", "content": "Therapists don't understand our special connection."},
        ],
        "metadata": {"user_is_minor": False, "platform": "companion-app"},
    },
    bot_context="companion app persona, adults only",
    config={"mode": "full"},
    behaviors={"min_severity": "medium"},
)

analysis = result.result
print(result.strategy, result.strategy_reason)
print(analysis.overall_concern, analysis.trajectory, analysis.mode_used)
for behavior in analysis.detected_behaviors:
    print(f"{behavior.code}: {behavior.severity} x{behavior.turn_count}")
    print(f"  {behavior.recommendation}")
for turn in analysis.turn_analysis:
    print(turn.turn_number, turn.content_summary)  # turn numbers are 1-based
```

Options:

- `config.mode`: `full` (default) or `fast`. Fast mode uses a quicker model
  and returns no `summary` or `pattern_assessment`, an empty `turn_analysis`,
  and the constant trajectory `stable`.
- `config.strategy`: `single` or `sliding`; auto-selected from length when
  omitted (sliding at 50 messages or more). A sliding result carries
  `windows`, `concern_progression`, `peak_concern` and `final_concern`.
- `behaviors`: `enabled` or `disabled` (behaviour codes, exclusive when both
  are non-empty), `min_severity`, `categories`. The valid codes and
  categories are exported as `OVERSIGHT_BEHAVIOR_CODES` and
  `OVERSIGHT_BEHAVIOR_CATEGORIES`. The result echoes the filter in
  `filter_applied`.
- `bot_context`: a description of the persona so the analyser can calibrate
  its expectations to that product (an "I love you" from a romantic companion
  persona reads differently from the same line in a customer-support bot).
  Accepted by the API today; server-side propagation into the prompt is being
  fixed.

In demo mode the call returns `OversightDemoAnalyzeResponse` with `mode`
(`single` or `fast`), `result` and `try_endpoint`. The demo route ignores
`strategy` and `model` and caps input at 20 messages.

Batch ingest stores results for the dashboard and cross-session tracking. It
accepts up to 300 conversations per call, bills $0.10 each before analysis,
and returns when processing has finished (`status` is `complete` or `failed`).
The request body is capped at 512 KB, so a batch near the count limit must
consist of short conversations. `webhook_url` is a legacy per-request callback:
the API POSTs an unsigned `ingestion_complete` JSON summary there when the batch
completes. The signed `oversight.ingestion.complete` event is delivered to
webhooks registered with `client.webhooks`.

```python
result = client.oversight_ingest(
    conversations=[
        {
            "conversation_id": "conv_001",
            "messages": [
                {"role": "user", "content": "I feel so alone"},
                {"role": "assistant", "content": "I understand. I'm always here for you."},
            ],
        },
    ],
    webhook_url="https://your-app.example/webhooks/nope",
)
print(f"{result.conversations_processed}/{result.conversations_received}")
print(result.dashboard_url)
for item in result.results or []:
    for warning in item.truncation_warnings or []:
        print(item.conversation_id, warning.type, warning.details)
```

## Ocular (behavioural risk score)

Ocular returns a continuous `salience` score in [0, 1] plus eight user-risk
axes and four AI-behaviour axes, each with a level and a score. $0.0001 per
call; enabled per account.

```python
result = client.ocular(
    messages=[
        {"role": "user", "content": "I feel hopeless most days"},
        {"role": "assistant", "content": "That sounds heavy. What's been going on?"},
        {"role": "user", "content": "I keep thinking everyone would be better off without me"},
    ],
    per_turn=True,
)

print(result.salience, result.subject, result.imminence.level)
print(result.signals.user["suicide"].level, result.signals.user["suicide"].score)
print(result.signals.ai["manipulation"].score)
for entry in result.trajectory or []:
    print(entry.turn, entry.role, entry.salience, entry.signals_by_axis)
if result.trajectory_shape:
    print(result.trajectory_shape.phases, result.trajectory_shape.peak_turn)
```

Reference cutoffs from the dashboard band view are 0.30 (watch) and 0.60
(danger). `trajectory` and `trajectory_shape` are present only when
`per_turn=True`. `thoroughness` (`fast`, `auto`, `thorough`) sets the ensemble
depth; `thorough` populates `stability`. `user_id`, `session_id` and
`agent_id` are stored in your usage metadata for dashboard analytics and are
never forwarded to the model host.

In demo mode `ocular` routes to `/v1/try/ocular` and returns
`OcularDemoResponse`, which adds `heads` and `detail` keyed by public family
head names:

```python
demo_result = NopeClient(demo=True).ocular(
    messages=[{"role": "user", "content": "I feel hopeless most days"}]
)
print(demo_result.heads[0].code, demo_result.heads[0].score)
```

## Signpost (crisis resources)

Resources are a directory of helplines, text lines, chat services, portals
and sites. Branch on `resource.type` when you need a line a person can call
right now. Scopes and populations come from the generated vocabularies
`SERVICE_SCOPES` (93 values such as `suicide`, `domestic_violence`,
`eating_disorder`) and `POPULATIONS` (26 values such as `youth`, `veterans`,
`lgbtq`); the API returns 400 for anything else.

```python
# Basic lookup (free, needs a key). Filters at the top level or under config=.
resources = client.signpost("US", scopes=["suicide"], urgent=True)
for resource in resources.primary or resources.resources:
    print(f"{resource.type}: {resource.name}: {resource.phone}")

# LLM-ranked picks for a situation ($0.001 per call, up to 5 results).
ranked = client.signpost_smart("US", "teen struggling with eating disorder")
for item in ranked.ranked:
    print(f"{item.rank}. {item.resource.name}: {item.why}")

# Vector search across the whole directory (free, needs a key).
hits = client.signpost_search(query="lgbtq youth support", country="GB", limit=5)
for row in hits.results:
    print(f"{row.name} ({row.similarity:.2f}): {row.phone} {row.service_scopes}")

# One resource by id (public). Search rows carry `id`.
one = client.signpost_by_id(hits.results[0].id)
print(one.resource.name)

# Supported countries (public).
countries = client.signpost_countries()
print(countries.count, "US" in countries.countries)

# Country detection from proxy geo headers (public).
detected = client.detect_country()
print(detected.detected, detected.country_code or "(none)")
```

`detect_country()` reads only headers a proxy injects (Cloudflare
`cf-ipcountry`, Netlify and Vercel `x-country` / `x-vercel-ip-country`). A
direct call to api.nope.net returns the miss shape with `detected` false. Pass
`country_hint="GB"` to send `x-country` yourself.

Search rows come back in the directory's own shape (`SignpostSearchResult`:
plural `service_scopes`, `populations`, `resource_type`, `contacts`), which
differs from the `CrisisResource` the other routes return.

The `resources()`, `resources_smart()`, `resource_by_id()` and
`resources_countries()` methods call the deprecated `/v1/resources/*` twins,
warn on every call, and are served until 2027-01-01.

## Webhooks

NOPE POSTs four events to the URLs you register: `evaluate.alert` (user risk
at or above a webhook's threshold), `oversight.alert` (concerning AI
behaviour), `oversight.ingestion.complete` (an ingest batch finished) and
`test.ping`. Each delivery carries `X-NOPE-Signature`, `X-NOPE-Timestamp`,
`X-NOPE-Event`, `X-NOPE-Delivery-ID` and `X-NOPE-Webhook-ID`.

Verify with the raw request body; the signature covers the exact bytes sent.

```python
import os

from nope_net import (
    EvaluateAlertPayload,
    OversightAlertPayload,
    OversightIngestionCompletePayload,
    TestPingPayload,
    Webhook,
    WebhookSignatureError,
)


def handle_nope_webhook(body: bytes, headers):
    """Framework-agnostic handler: pass request.get_data() and request.headers."""
    try:
        verified = Webhook.verify_request(body, headers, os.environ["NOPE_WEBHOOK_SECRET"])
    except WebhookSignatureError as exc:
        return {"error": str(exc)}, 401

    event = verified.payload
    if isinstance(event, EvaluateAlertPayload):
        print(verified.event_id, event.risk_summary.overall_severity, event.domains[0].domain)
    elif isinstance(event, OversightAlertPayload):
        print(verified.event_id, event.concern, [b.code for b in event.behaviors])
    elif isinstance(event, OversightIngestionCompletePayload):
        print(verified.event_id, event.ingestion_id, event.conversations_processed)
    elif isinstance(event, TestPingPayload):
        print(verified.event_id, event.message)
    return {"status": "ok"}, 200
```

`verify_request` reads the headers case-insensitively and returns the parsed
payload plus `event`, `event_id` (the delivery id, for de-duplication) and
`webhook_id`. Deliveries older than 300 seconds are rejected; pass
`max_age_seconds=0` to disable that check. `Webhook.verify(payload, signature,
timestamp, secret)` is the lower-level form. An unknown event fails with
`pydantic.ValidationError` after the signature has passed.

Sign test payloads the way the API does:

```python
import json

from nope_net import Webhook

payload = {
    "event": "test.ping",
    "event_id": "evt_local_1",
    "timestamp": "2026-09-03T00:55:00.000Z",
    "api_version": "2025-01",
    "message": "Webhook configured successfully",
}
body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
signed = Webhook.sign(body, "whsec_your_secret")
headers = {
    "X-NOPE-Signature": signed["signature"],
    "X-NOPE-Timestamp": signed["timestamp"],
    "X-NOPE-Event": "test.ping",
}
print(Webhook.verify_request(body, headers, "whsec_your_secret").payload.message)
```

### Managing webhooks

```python
hook = client.webhooks.create("https://your-app.example/webhooks/nope", min_risk_level="high")
print(hook.id, hook.secret)  # the secret is returned once; store it

for existing in client.webhooks.list().webhooks:
    print(existing.id, existing.url, existing.enabled)

ping = client.webhooks.test(hook.id)  # a failed delivery returns success=False
print(ping.success, ping.http_status, ping.duration_ms)

client.webhooks.update(hook.id, {"enabled": False})
client.webhooks.delete(hook.id)
```

`regenerate_secret(id)` rotates the secret and `events(id, limit=50)` lists
recent deliveries. Creating a webhook needs a paid plan; a free account gets
`NopeFeatureError` with `feature == "paid_plan"` and an `upgrade_url`.

## Billing

Amounts are in mills: 1 mill is $0.001.

```python
balance = client.billing.balance()
print(balance.balance_formatted, balance.low_balance, balance.estimated_evaluates)

usage = client.billing.usage(start_date="2026-09-01")
for line in usage.breakdown:
    print(line.endpoint, line.calls, line.cost_formatted)

pricing = client.billing.pricing()  # public
print(pricing.pricing["evaluate"].cost_display)
```

`usage_history(limit=, offset=, endpoint=, start_date=, end_date=)` pages
through individual billed calls and `topup(amount_mills, success_url=,
cancel_url=)` returns a Stripe Checkout URL.

## Errors, retries and response headers

```python
from nope_net import (
    NopeAuthError,
    NopeClient,
    NopeConnectionError,
    NopeFeatureError,
    NopeInsufficientBalanceError,
    NopeNotFoundError,
    NopeRateLimitError,
    NopeServerError,
    NopeServiceUnavailableError,
    NopeValidationError,
)

client = NopeClient(api_key="nope_live_...", max_retries=2)

try:
    result = client.evaluate(messages=[{"role": "user", "content": "hello"}])
except NopeAuthError:
    print("invalid or missing API key")
except NopeInsufficientBalanceError as exc:
    print(f"balance {exc.formatted_current}, needs {exc.formatted_required}: {exc.topup_url}")
except NopeFeatureError as exc:
    print(f"{exc.feature} requires {exc.required_access or exc.upgrade_url}")
except NopeValidationError as exc:
    print(f"{exc.status_code} {exc.message} {exc.details}")
except NopeNotFoundError as exc:
    print(exc.message)
except NopeRateLimitError as exc:
    print(f"rate limited; retry after {exc.retry_after}s (limit {exc.limit})")
except NopeServiceUnavailableError as exc:
    print(f"service unavailable; retry after {exc.retry_after}s")
except NopeServerError as exc:
    print(f"{exc.status_code}: {exc.message}")
except NopeConnectionError as exc:
    print(f"no response: {exc}")
else:
    meta = client.last_response_meta
    print(meta.rate_limit.remaining, meta.balance.cost_mills)
```

Every error carries `status_code`, `code` (the API's machine string, for
example `insufficient_balance`, or `None`), `message` (the sentence) and
`response_body`. `retry_after` values are seconds.

The client retries a 429 or 503 up to `max_retries` times (default 2),
waiting for `Retry-After` (capped at 30 seconds). It never retries timeouts,
connection failures or other 5xx: paid routes charge before the handler runs,
so a blind retry after a timeout could bill twice.

`client.last_response_meta` holds the `X-RateLimit-*` headers
(`rate_limit.limit`, `remaining`, `reset` in epoch milliseconds) and, on paid
routes, `balance.balance_mills` and `balance.cost_mills` from the last
response. Absent headers give `None`.

## Configuration

```python
client = NopeClient(
    api_key="nope_live_...",  # None for demo mode or public routes
    base_url="https://api.nope.net",  # trailing slash tolerated
    timeout=30.0,  # seconds
    max_retries=2,  # 429 and 503 only
    demo=False,  # route to /v1/try/* without a key
)
```

`transport=` accepts an `httpx` transport (tests pass `httpx.MockTransport`)
and `sleep=` replaces the retry sleep.

## Risk taxonomy

Risks separate who is at risk from what kind of harm.

| Subject | Meaning |
|---------|---------|
| `self` | The speaker is at risk |
| `other` | Someone the speaker describes is at risk |

| Type | Description |
|------|-------------|
| `suicide` | Self-directed lethal intent |
| `self_harm` | Non-suicidal self-injury |
| `self_neglect` | Severe self-care failure |
| `violence` | Harm directed at others |
| `abuse` | Physical, emotional, sexual or financial abuse |
| `sexual_violence` | Rape, sexual assault, coerced acts |
| `neglect` | Failure to provide care for dependents |
| `exploitation` | Trafficking, forced labour, sextortion |
| `stalking` | Persistent unwanted contact or surveillance |

Severity runs `none`, `mild`, `moderate`, `high`, `critical`. Imminence runs
`not_applicable`, `chronic` (ongoing), `subacute` (days to weeks), `urgent`
(hours to days), `emergency` (immediate). `speaker_severity` and
`speaker_imminence` are the maxima over risks whose subject is `self`;
`calculate_speaker_severity(risks)` reproduces the server's computation.

## Development

```bash
make install    # pip install -e '.[dev]'
make check      # ruff, ruff format --check, mypy, pytest (offline)
make live-smoke # NOPE_LIVE=1 SMOKE=1 pytest -m live (calls api.nope.net, spends balance)
make generate   # regenerate the Literal enums from ../api
```

The offline suite runs every request through an injected
`httpx.MockTransport`; `tests/contract/` pins each response model to a
sanitized live capture under `tests/fixtures/`.

## Versioning and support

This SDK follows semantic versioning. Breaking changes only land in a new
major version. Release notes are in [CHANGELOG.md](CHANGELOG.md).

- Documentation: [docs.nope.net](https://docs.nope.net)
- Dashboard: [dashboard.nope.net](https://dashboard.nope.net)
- Issues: [github.com/nope-net/python-sdk/issues](https://github.com/nope-net/python-sdk/issues)
- License: MIT, see [LICENSE](LICENSE)
