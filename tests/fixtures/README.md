# Contract fixtures

Sanitized responses captured from the live API at `https://api.nope.net` on 2026-09-03
(API commit 73c477c). They are the reference wire shapes for the offline contract tests:
every fixture must parse into the SDK's response type without a cast, and every
documented field must be typed.

Never edit these by hand. Regenerate them from a live run (see the E2E suite) and keep
the sanitization rules below.

| Folder | Files | Call |
|---|---|---|
| `evaluate/` | `auth.benign.json` | `POST /v1/evaluate`, one benign message, `risks: []` |
| | `try.gb.json` | `POST /v1/try/evaluate`, three messages, GB resources, `subdivision_codes`, `metadata.model` |
| | `try.us.json` | `POST /v1/try/evaluate`, one message; requested with `config.country: GB` before the demo route honoured it, so the resources are US |
| `oversight/` | `try.full.json`, `try.fast.json`, `auth.fast.json` | the demo full, demo fast and authenticated fast envelopes |
| `ocular/` | `try.json`, `auth.json` | demo wire (with `heads`, `detail`) and customer wire, `meta.version` 0.3.11 |
| `signpost/` | `auth.gb.json`, `try.smart.json`, `search.auth.json`, `search.auth.mixed-contacts.json`, `countries.json`, `detect-country.miss.json` | basic (authenticated), demo smart, search (authenticated; the mixed-contacts capture from the first live run shows contacts without `tier` or `value` and chat contacts carrying `url`), countries, detect-country miss |
| `billing/` | `balance.json`, `usage.json`, `pricing.json` | `GET /v1/billing/*` (balance and usage figures replaced) |
| `errors/` | `400.*.json`, `401.*.json`, `404.*.json`, `413.*.json` | error bodies as served; 402, 429 and 503 are source-derived and live in the tests |
| `headers/` | `*.txt` | rate-limit and balance headers (balance values replaced) |
| `webhooks/` | `*.json` | payloads built by the API's own builders and signed with a fixed test secret |

Sanitization rules:

- `request_id` becomes `eval_1788396900000_fixture`; `timestamp` and `analyzed_at` become `2026-09-03T00:55:00.000Z`
- `latency_ms` becomes 1000, `inference_ms` 50, search `timing` 120/30/150, `open_status.next_change` a fixed instant
- balance, usage and top-up figures are replaced with small round numbers
- helpline records are the public directory and are kept verbatim
- nothing carries an API key, a real user id, or a real conversation
