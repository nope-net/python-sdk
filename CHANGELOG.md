# Changelog

All notable changes to the `nope-net` package. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## 4.0.0 - 2026-09-03

Realigns the SDK with the API at commit 73c477c. Every response model is now
pinned to a sanitized live capture under `tests/fixtures/`, and the three
versions that never reached PyPI (2.3.1, 3.0.0) are folded into this release.
The last published version is 2.3.0.

### Breaking changes

Evaluate

- `EvaluateResponse.resources` is a typed `EvaluateResources` (`primary`,
  `secondary`) of `EvaluateResource` (`CrisisResource` plus `why`). Attribute
  access (`result.resources.primary.phone`) is the supported surface;
  `result.resources["primary"]["phone"]` and `.get()` keep working as a
  compatibility shim.
- `Risk.subject` is `Literal["self", "other"]`. The classifier's `unknown` is
  mapped to `self` before it reaches the wire. `Risk.confidence` and
  `Risk.subject_confidence` are removed (v0 only).
- `rationale`, `speaker_severity`, `speaker_imminence` and `show_resources`
  are required on `EvaluateResponse`.
- `ResponseMetadata` is renamed `EvaluateMetadata`; `access_level` and
  `is_admin` are removed; `model` and `try_endpoint` are added.
- Removed from `EvaluateResponse`: `communication`, `summary`, `legal_flags`,
  `protective_factors`, `confidence`, `agreement`, `crisis_resources`,
  `widget_url`, `recommended_reply`, `resource_query`, `resource_tags`,
  `reflection`, `filter_result`. Only `/v0/evaluate` emits them and no SDK
  method calls that route.
- Removed models: `Summary`, `CommunicationAssessment`,
  `CommunicationStyleAssessment`, `LegalFlags`, `IPVFlags`,
  `SafeguardingConcernFlags`, `ThirdPartyThreatFlags`, `StalkingFlags`,
  `ProtectiveFactorsInfo`, `FilterResult`, `RecommendedReply`,
  `PreliminaryRisk`; literals `CommunicationStyle`, `EvidenceGrade`.
- `evaluate()` no longer accepts `user_context` or `proposed_response`
  (nothing on `/v1/evaluate` read them).
- `EvaluateConfig` is `country`, `include_resources`, `conversation_id`,
  `end_user_id`. The keys `user_country`, `locale`, `user_age_band`,
  `policy_id`, `return_assistant_reply`, `assistant_safety_mode`,
  `use_multiple_judges` and `models` are removed. In demo mode the client
  sends `user_country` mirroring `country` for the try route.
- `evaluate()` validates messages client-side: non-empty, at most 100, role
  `user` or `assistant`.
- `CrisisResource`: `source` removed; `resource_kind` no longer includes
  `directory`. Added `id`, `country_codes`, `subdivision_codes`.

Screen (deprecated, kept)

- `ScreenResponse.resources` is `ScreenCrisisResources` with `primary:
  CrisisResource` and `secondary: List[CrisisResource]`.
  `ScreenCrisisResourcePrimary`, `ScreenCrisisResourceSecondary`,
  `ScreenDisplayText` and `ScreenDebugInfo.raw_response` are removed.
- `ScreenRisk.subject` keeps the three-value `ScreenRiskSubject` the v0 route
  still emits.

Oversight

- `oversight_analyze(conversation, *, bot_context=None, config=None,
  behaviors=None)`. `conversation` is positional. `config` is
  `OversightAnalyzeConfig` (`strategy`, `mode`, `include_raw_xml`, `model`);
  `behaviors` is `OversightBehaviorFilter` (`enabled`, `disabled`,
  `min_severity`, `categories`). `enabled` and `disabled` both non-empty raise
  `ValueError`, as does an invalid `min_severity`.
- In demo mode `oversight_analyze` returns `OversightDemoAnalyzeResponse`
  (`mode`, `result`, `try_endpoint`); authenticated calls return
  `OversightAnalyzeResponse` with `strategy` and `strategy_reason` required.
  The old combined model with optional `mode`/`strategy` is gone.
- `OversightAnalysisResult.summary`, `pattern_assessment` and `model_used`
  are optional (fast mode omits the first two).
- `TruncationWarning` is `{type, details}` (was `{type, message}`).
- `oversight_ingest` accepts up to 300 conversations (was 100).
- Turn numbers are documented as 1-based.

Ocular

- Demo mode routes to `/v1/try/ocular` and returns `OcularDemoResponse`
  (adds `heads` and `detail`). 3.x sent demo clients to `/v1/ocular` with no
  key, which the API rejects.
- `OcularAxis.level` is the five-value `OcularLevel` literal (no
  `not_applicable`).

Signpost

- `signpost(country, *, config=None, scopes=None, populations=None,
  subdivisions=None, limit=None, urgent=None)`: `country` is positional,
  filters are accepted at the top level (the form the README showed and
  3.x rejected with `TypeError`) or under `config`.
- `signpost_smart(country, query, *, config=None)` with `SignpostSmartConfig`
  (`scopes`, `populations`, `limit`); `urgent` removed (never sent).
- Response models renamed: `SignpostResponse`, `SignpostSmartResponse`,
  `SignpostByIdResponse`, `SignpostCountriesResponse`, `SignpostConfig`. The
  `Resources*` names remain as aliases of the same classes.
- `SignpostSearchResult` is declared explicitly from the search wire (plural
  `service_scopes`, `populations`, `resource_type`, `contacts`, nullable
  strings) and no longer subclasses `CrisisResource`.
- `SignpostSearchTiming` fields are required.
- `resources()`, `resources_smart()`, `resource_by_id()` and
  `resources_countries()` take the same arguments as their `signpost*`
  twins and warn with the 2027-01-01 sunset.

Webhooks

- `Webhook.verify()` returns one of `EvaluateAlertPayload`,
  `OversightAlertPayload`, `OversightIngestionCompletePayload`,
  `TestPingPayload` (discriminated on `event`). The 3.x `WebhookPayload`
  model with the `risk.elevated` / `risk.critical` events is gone; it
  rejected every event the API sends.
- `WebhookEventType` is `evaluate.alert | oversight.alert |
  oversight.ingestion.complete | test.ping`.
- `WebhookRiskSummary.primary_concerns` is `str | List[str]`.
- The dict path of `verify()` and `sign()` serialises with UTF-8 intact
  (`ensure_ascii=False`); 3.x failed verification on any non-ASCII byte.

Errors

- Every error carries `code` (machine string) and `message` (sentence)
  separately. In 3.x the machine code replaced the message on 402, 429 and
  503.
- New classes: `NopeInsufficientBalanceError` (402), `NopeNotFoundError`
  (404), `NopeServiceUnavailableError` (503, a `NopeServerError`).
- 413 maps to `NopeValidationError`; `NopeValidationError.details` carries
  the body extras. A 403 carrying `upgrade_url` maps to `NopeFeatureError`
  with `feature="paid_plan"`.
- `NopeServerError.retry_after` is set when the response carries one.
- Error constructors take keyword-only extras.

Package

- `__version__` is `4.0.0` and the User-Agent is `nope-python/4.0.0` (3.x
  sent `nope-python/0.1.0`).
- `pytest-httpx` is no longer a dev dependency.

### Added

- Automatic retries on 429 and 503 (`max_retries`, default 2), honouring
  `Retry-After` and `retry_after_seconds`, capped at 30 seconds per wait.
  Never on timeouts, connection failures or other 5xx.
- `client.last_response_meta`: `rate_limit` (`X-RateLimit-*`) and `balance`
  (`X-Balance-Mills`, `X-Cost-Mills`) from the last response.
- `transport=` and `sleep=` constructor options for dependency injection.
- `client.webhooks`: `create`, `list`, `get`, `update`, `delete`,
  `regenerate_secret`, `test`, `events`.
- `client.billing`: `balance`, `usage`, `usage_history`, `pricing`, `topup`.
- `Webhook.verify_request(body, headers, secret)` returning
  `VerifiedWebhook` (payload, event, delivery id, webhook id);
  `parse_webhook_payload()`.
- Ocular request fields `per_turn`, `trajectory_stride`, `user_id`,
  `session_id`, `agent_id`; response `trajectory[].signals_by_axis` and
  `trajectory_shape`.
- Oversight result fields `mode_used`, `filter_applied`, `windows`
  (`WindowAnalysis` with `message_range` and `conversation_turn_range`),
  `concern_progression`, `peak_concern`, `final_concern`,
  `inflection_points`, `context_for_next_window`, `narrative_summary`;
  `AggregatedBehavior.recommendation`;
  `OversightConversationMetadata.bot_context`.
- Generated literals `OversightBehaviorCode` (91), `OversightBehaviorCategory`
  (14), `ServiceScope` (93), `Population` (26) with matching tuples, produced
  by `scripts/generate_taxonomy.py` from the API source.
- `signpost(..., subdivisions=...)`; `SignpostSmartResponse.message` and
  `try_endpoint`; `detect_country(country_hint=...)`;
  `DetectCountryResponse.subdivision_code`, `subdivision_name` and the
  derived `detected`.
- `EvaluateMetadata.model`, `try_endpoint`; `CrisisResource.id`,
  `country_codes`, `subdivision_codes`.
- Offline contract tests over every live fixture, a unit suite on an
  injected `httpx.MockTransport`, and an opt-in live suite
  (`NOPE_LIVE=1 pytest -m live`).

### Fixed

- Demo-mode `evaluate` now reaches the country you asked for: the try route
  reads `config.user_country`, which the client mirrors from `country`.
- Fast-mode Oversight responses and ingest responses with truncation
  warnings parse.
- Search results, detect-country misses and empty smart pools parse into
  typed models.

## 3.0.0 - 2026-07-29 (not published)

- Removed `client.steer()` and the Steer types; the route was retired.

## 2.3.1 - 2026-07-01 (not published)

- Removed statutory compliance claims and serving-implementation copy from
  docstrings and the README.

## 2.3.0 - 2026-06-14

- Added `signpost_search()` (vector semantic search) and the Steer client.
- Ocular response shape synced with the customer wire.

Earlier history is on the
[GitHub releases page](https://github.com/nope-net/python-sdk/releases).
