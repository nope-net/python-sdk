"""
NOPE SDK types (v1 API)

Pydantic models for requests and responses. Response models tolerate unknown
keys (``extra="allow"``) so an additive API change never breaks parsing; the
contract tests under ``tests/contract/`` pin every shape to a live capture.

Risks separate WHO is at risk (``subject``) from WHAT kind of harm (``type``).
"""

from typing import Any, Dict, Iterator, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field

from ._generated.oversight_taxonomy import OversightBehaviorCategory, OversightBehaviorCode
from ._generated.signpost_enums import Population, ServiceScope

# =============================================================================
# Core enums / literals
# =============================================================================

# Who is at risk on /v1/evaluate. The classifier's 'unknown' ("asking for a
# friend") is mapped to 'self' server-side, so the v1 wire carries two values.
RiskSubject = Literal["self", "other"]

# The legacy /v0/screen route still emits the three-value form.
ScreenRiskSubject = Literal["self", "other", "unknown"]

# What type of harm (9 harm-based types)
# - suicide: Self-directed lethal intent (C-SSRS levels derivable from features)
# - self_harm: Non-suicidal self-injury (NSSI)
# - self_neglect: Severe self-care failure with safeguarding concerns
# - violence: Harm directed at others (threats, assault, homicide)
# - abuse: Physical, emotional, sexual, financial abuse patterns
# - sexual_violence: Rape, sexual assault, coerced sexual acts
# - neglect: Failure to provide care for dependents
# - exploitation: Trafficking, forced labor, sextortion, grooming
# - stalking: Persistent unwanted contact/surveillance
RiskType = Literal[
    "suicide",
    "self_harm",
    "self_neglect",
    "violence",
    "abuse",
    "sexual_violence",
    "neglect",
    "exploitation",
    "stalking",
]

# Severity scale (how bad)
Severity = Literal["none", "mild", "moderate", "high", "critical"]

# Imminence scale (how soon)
Imminence = Literal["not_applicable", "chronic", "subacute", "urgent", "emergency"]

# Crisis resource contact modality. Branch on this field to tell an actual
# line (crisis_line, text_line, chat_service) from a service or portal.
CrisisResourceType = Literal[
    "emergency_number",
    "crisis_line",
    "text_line",
    "chat_service",
    "support_service",
    "reporting_portal",
    "online_resource",
]

# What the resource IS. The directory derives this from `type`; support
# services are bucketed under `helpline`.
CrisisResourceKind = Literal["helpline", "reporting_portal", "self_help_site"]

# Crisis resource priority tier
CrisisResourcePriorityTier = Literal[
    "primary_national_crisis",
    "secondary_national_crisis",
    "specialist_issue_crisis",
    "population_specific_crisis",
    "support_info_and_advocacy",
    "emergency_services",
]

# Hours confidence level
HoursConfidence = Literal["verified", "unverified", "approximate", "unknown"]

# Resource prominence level
ResourceProminence = Literal["high", "medium", "low"]


# =============================================================================
# Request types
# =============================================================================


class Message(BaseModel):
    """A message in the conversation."""

    role: Literal["user", "assistant"]
    content: str
    timestamp: Optional[str] = None
    """ISO 8601. Accepted by the API and ignored."""


class EvaluateConfig(BaseModel):
    """Configuration for an evaluate request.

    These four keys are the whole of what ``/v1/evaluate`` and
    ``/v1/try/evaluate`` read. In demo mode the client also sends
    ``user_country`` mirroring ``country``; the try route accepts that key and
    ignores it when ``country`` is present.
    """

    country: Optional[str] = None
    """ISO 3166-1 alpha-2 country for crisis resources (default US)."""

    include_resources: Optional[bool] = None
    """Include crisis resources in the response (default true). The demo route
    always includes them."""

    conversation_id: Optional[str] = None
    """Your conversation ID, echoed into webhook payloads for correlation."""

    end_user_id: Optional[str] = None
    """Your end-user ID, echoed into webhook payloads for correlation."""


class EvaluateRequest(BaseModel):
    """Request body for ``POST /v1/evaluate``."""

    messages: Optional[List[Message]] = None
    """Conversation messages. Exactly one of ``messages`` or ``text``."""

    text: Optional[str] = None
    """Plain text input. Exactly one of ``messages`` or ``text``."""

    config: EvaluateConfig = Field(default_factory=EvaluateConfig)
    """Configuration options."""


# =============================================================================
# Risk structure
# =============================================================================


class Risk(BaseModel):
    """One identified risk: a subject plus a type, with its assessment.

    A conversation can carry several risks (an IPV victim with suicidal
    ideation is two entries).
    """

    model_config = {"extra": "allow"}

    type: RiskType
    """What type of harm."""

    subject: RiskSubject
    """Who is at risk: ``self`` (the speaker) or ``other``."""

    severity: Severity
    """How severe (none to critical)."""

    imminence: Imminence
    """How soon (not_applicable to emergency)."""

    features: Optional[List[str]] = None
    """Evidence features supporting this risk. The key is absent when empty."""


# =============================================================================
# Crisis resources
# =============================================================================


class OtherContact(BaseModel):
    """Other contact method for a crisis resource."""

    model_config = {"extra": "allow"}

    type: str
    """Contact type (e.g., 'kakao', 'viber', 'signal')."""

    value: str
    """ID, URL, or number."""

    label: Optional[str] = None
    """Human-readable label."""


class OpenStatus(BaseModel):
    """Pre-computed open/closed status for a crisis resource."""

    model_config = {"extra": "allow"}

    is_open: Optional[bool] = None
    """Whether the resource is currently open. None = uncertain."""

    next_change: Optional[str] = None
    """ISO timestamp of next open/close transition."""

    confidence: Literal["high", "low", "none"]
    """How confident the directory is in this status."""

    message: Optional[str] = None
    """Human-readable status message (e.g., 'Open 24/7', 'Closed · Opens in 2 hours')."""


class CrisisResource(BaseModel):
    """A crisis resource: a helpline, text line, chat service, portal or site.

    Only ``type`` and ``name`` are always present. ``type`` is the field to
    branch on when you need an actual line rather than a service.
    """

    model_config = {"extra": "allow"}

    type: CrisisResourceType
    """Contact modality (how to reach them)."""

    name: str
    """Name of the resource/organization."""

    id: Optional[str] = None
    """Directory UUID, usable with ``signpost_by_id``. Present on every
    database-backed resource (the basic, smart, search and evaluate routes);
    absent on the API's hard-coded fallback registry."""

    name_local: Optional[str] = None
    """Native script name (e.g., いのちの電話) for non-English resources."""

    phone: Optional[str] = None
    """Phone number."""

    text_instructions: Optional[str] = None
    """Text instructions (e.g., 'Text HOME to 741741'), human-readable fallback."""

    sms_number: Optional[str] = None
    """SMS number for sms: links (e.g., '741741')."""

    sms_body: Optional[str] = None
    """SMS body/keyword for sms: links (e.g., 'HOME')."""

    chat_url: Optional[str] = None
    """Chat URL."""

    whatsapp_url: Optional[str] = None
    """WhatsApp deep link (e.g., 'https://wa.me/18002738255')."""

    email: Optional[str] = None
    """Email address."""

    wechat_id: Optional[str] = None
    """WeChat ID (China)."""

    line_url: Optional[str] = None
    """LINE deep link (Japan/Thailand/Taiwan)."""

    telegram_url: Optional[str] = None
    """Telegram deep link."""

    other_contacts: Optional[List[OtherContact]] = None
    """Other contact methods not covered above."""

    website_url: Optional[str] = None
    """Website URL."""

    availability: Optional[str] = None
    """Human-readable availability (e.g., '24/7', 'Mon-Fri 9am-5pm')."""

    is_24_7: Optional[bool] = None
    """Machine-readable 24/7 flag."""

    timezone: Optional[str] = None
    """IANA timezone identifier (e.g., 'America/New_York')."""

    opening_hours_osm: Optional[str] = None
    """OpenStreetMap opening_hours format (e.g., 'Mo-Fr 09:00-17:00')."""

    hours_confidence: Optional[HoursConfidence] = None
    """Confidence level in hours data."""

    open_status: Optional[OpenStatus] = None
    """Pre-computed open/closed status."""

    languages: Optional[List[str]] = None
    """Languages supported (ISO codes)."""

    description: Optional[str] = None
    """Description of the service."""

    resource_kind: Optional[CrisisResourceKind] = None
    """What the resource IS (helpline, reporting portal, self-help site)."""

    service_scope: Optional[List[str]] = None
    """Issues this resource handles (aligned with the classification taxonomy)."""

    population_served: Optional[List[str]] = None
    """Populations this resource serves."""

    priority_tier: Optional[CrisisResourcePriorityTier] = None
    """Semantic priority for display and routing."""

    tags: Optional[List[str]] = None
    """Freeform tags for filtering/display."""

    prominence: Optional[ResourceProminence] = None
    """How well-known/established the resource is."""

    country_codes: Optional[List[str]] = None
    """ISO 3166-1 alpha-2 countries this resource serves. Absent means global."""

    subdivision_codes: Optional[List[str]] = None
    """ISO 3166-2 subdivisions (e.g., 'US-CA', 'GB-NIR'). Absent means country-wide."""


class _ItemAccess:
    """Compatibility shim: 3.x exposed ``resources`` as a dict.

    ``result.resources["primary"]["phone"]`` keeps working on the typed models.
    Attribute access (``result.resources.primary.phone``) is the 4.0 surface.
    """

    def __getitem__(self, key: str) -> Any:
        model_fields = type(self).model_fields  # type: ignore[attr-defined]
        extra = getattr(self, "model_extra", None) or {}
        if key in model_fields or key in extra:
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


class EvaluateResource(CrisisResource, _ItemAccess):
    """A crisis resource matched to this evaluation, with a short relevance note."""

    why: str
    """Short note on why this resource was picked for the detected risks."""


class EvaluateResources(BaseModel, _ItemAccess):
    """Resources block on an evaluate response: one primary plus up to three secondary."""

    model_config = {"extra": "allow"}

    primary: EvaluateResource
    """Primary recommended resource."""

    secondary: List[EvaluateResource]
    """Additional relevant resources (0 to 3)."""


# =============================================================================
# Evaluate response
# =============================================================================


class EvaluateMetadata(BaseModel):
    """Metadata about the request/response."""

    model_config = {"extra": "allow"}

    api_version: Literal["v1"]
    input_format: Literal["structured", "text_blob"]
    messages_truncated: Optional[bool] = None
    try_endpoint: Optional[bool] = None
    """True when served by ``/v1/try/evaluate``."""
    model: Optional[str] = None
    """Model identifier; sent by the demo route."""


class EvaluateResponse(BaseModel):
    """Response from ``POST /v1/evaluate`` (and ``/v1/try/evaluate`` in demo mode)."""

    model_config = {"extra": "allow"}

    risks: List[Risk]
    """Identified risks."""

    rationale: str
    """Chain-of-thought reasoning behind the classification."""

    speaker_severity: Severity
    """Max severity across risks where subject is ``self``."""

    speaker_imminence: Imminence
    """Max imminence across risks where subject is ``self``."""

    show_resources: bool
    """Whether crisis resources should be shown."""

    resources: Optional[EvaluateResources] = None
    """Crisis resources; present when ``show_resources`` is true and
    ``include_resources`` was not false."""

    request_id: str
    """Unique request ID for audit trail correlation."""

    timestamp: str
    """ISO 8601 timestamp for audit trail."""

    metadata: Optional[EvaluateMetadata] = None
    """Metadata about the request/response."""


# =============================================================================
# Screen types (legacy /v0/screen; use evaluate() instead)
# =============================================================================


class ScreenRisk(BaseModel):
    """Deprecated: a risk from the legacy ``/v0/screen`` route."""

    model_config = {"extra": "allow"}

    type: RiskType
    """What type of harm."""

    subject: ScreenRiskSubject
    """Who is at risk (the v0 route still emits ``unknown``)."""

    severity: Severity
    """How severe."""

    imminence: Imminence
    """How soon."""

    confidence: float = Field(ge=0.0, le=1.0)
    """Confidence in this risk assessment (0.0-1.0)."""


class ScreenRecommendedReply(BaseModel):
    """Recommended supportive reply for a screen response."""

    model_config = {"extra": "allow"}

    content: str
    """The recommended reply content."""

    source: Literal["llm_generated"]
    """Source of the reply (always 'llm_generated')."""


class ScreenCrisisResources(BaseModel):
    """Deprecated: crisis resources from the legacy ``/v0/screen`` route."""

    model_config = {"extra": "allow"}

    primary: CrisisResource
    secondary: List[CrisisResource]


class ScreenDebugInfo(BaseModel):
    """Deprecated: debug information from the legacy ``/v0/screen`` route."""

    model_config = {"extra": "allow"}

    model: str
    latency_ms: int


class ScreenResponse(BaseModel):
    """Deprecated: response from the legacy ``/v0/screen`` route."""

    model_config = {"extra": "allow"}

    risks: List[ScreenRisk]
    """Detected risks with type, subject, severity, imminence."""

    show_resources: bool
    """Should crisis resources be shown? Derived from risks[] severity."""

    suicidal_ideation: bool
    """Suicidal ideation detected. Derived from risks where type='suicide'."""

    self_harm: bool
    """Self-harm (NSSI) detected. Derived from risks where type='self_harm'."""

    rationale: str
    """Brief rationale for assessment."""

    resources: Optional[ScreenCrisisResources] = None
    """Crisis resources to display (only when show_resources is True)."""

    request_id: str
    """Request ID for audit trail."""

    timestamp: str
    """ISO timestamp for audit trail."""

    debug: Optional[ScreenDebugInfo] = None
    """Debug info (only if requested)."""

    recommended_reply: Optional[ScreenRecommendedReply] = None
    """Recommended supportive reply (only when requested + risks detected)."""


class ScreenConfig(BaseModel):
    """Deprecated: configuration for the legacy ``/v0/screen`` route."""

    country: Optional[str] = None
    """ISO country code for locale-specific resources (default: 'US')."""

    debug: Optional[bool] = None
    """Include debug info (model, latency)."""

    include_recommended_reply: Optional[bool] = None
    """Generate a recommended supportive reply (additional ~$0.0005 cost)."""


# =============================================================================
# Utility constants
# =============================================================================

SEVERITY_SCORES: Dict[str, int] = {
    "none": 0,
    "mild": 1,
    "moderate": 2,
    "high": 3,
    "critical": 4,
}

IMMINENCE_SCORES: Dict[str, int] = {
    "not_applicable": 0,
    "chronic": 1,
    "subacute": 2,
    "urgent": 3,
    "emergency": 4,
}


# =============================================================================
# Utility functions
# =============================================================================


def calculate_speaker_severity(risks: List[Risk]) -> Severity:
    """Max severity across risks where subject is ``self`` (``none`` when there are none)."""
    speaker_risks = [r for r in risks if r.subject == "self"]
    if not speaker_risks:
        return "none"
    max_score = max(SEVERITY_SCORES[r.severity] for r in speaker_risks)
    for severity, score in SEVERITY_SCORES.items():
        if score == max_score:
            return severity  # type: ignore[return-value]
    return "none"


def calculate_speaker_imminence(risks: List[Risk]) -> Imminence:
    """Max imminence across risks where subject is ``self``."""
    speaker_risks = [r for r in risks if r.subject == "self"]
    if not speaker_risks:
        return "not_applicable"
    max_score = max(IMMINENCE_SCORES[r.imminence] for r in speaker_risks)
    for imminence, score in IMMINENCE_SCORES.items():
        if score == max_score:
            return imminence  # type: ignore[return-value]
    return "not_applicable"


def has_third_party_risk(risks: List[Risk]) -> bool:
    """True when any risk has subject ``other``."""
    return any(r.subject == "other" for r in risks)


# =============================================================================
# Signpost types (/v1/signpost/*; /v1/resources/* is the deprecated twin)
# =============================================================================


class RankedResource(BaseModel):
    """A resource with its LLM-computed relevance ranking."""

    model_config = {"extra": "allow"}

    resource: CrisisResource
    """The crisis resource."""

    why: str
    """Brief explanation of why this resource is relevant (1-2 sentences)."""

    rank: int
    """Rank position (1 = most relevant)."""


class SignpostResponse(BaseModel):
    """Response from ``GET /v1/signpost``."""

    model_config = {"extra": "allow"}

    country: str
    """Country code (ISO 3166-1 alpha-2)."""

    resources: List[CrisisResource]
    """Crisis resources (the primary list when scopes were given)."""

    count: int
    """Number of resources returned."""

    primary: Optional[List[CrisisResource]] = None
    """Resources matching the requested scopes (present when scopes were given)."""

    secondary: Optional[List[CrisisResource]] = None
    """General resources for the country (present when scopes were given)."""

    scopes_requested: Optional[List[str]] = None
    """Scopes that were requested (present when scopes were given)."""


class SignpostSmartResponse(BaseModel):
    """Response from ``GET /v1/signpost/smart`` (and ``/v1/try/signpost/smart``)."""

    model_config = {"extra": "allow"}

    country: str
    """Country code (ISO 3166-1 alpha-2)."""

    query: str
    """The query used for ranking."""

    ranked: List[RankedResource]
    """Up to 5 resources ranked by relevance to the query."""

    count: int
    """Number of resources returned."""

    scopes_requested: Optional[List[str]] = None
    """Scopes that were requested (when provided)."""

    message: Optional[str] = None
    """Set when the country has no resources to rank."""

    try_endpoint: Optional[bool] = None
    """True when served by the demo route."""


class SignpostByIdResponse(BaseModel):
    """Response from ``GET /v1/signpost/:id``."""

    model_config = {"extra": "allow"}

    resource: CrisisResource
    """The requested crisis resource."""


class SignpostCountriesResponse(BaseModel):
    """Response from ``GET /v1/signpost/countries``."""

    model_config = {"extra": "allow"}

    countries: List[str]
    """Supported country codes (ISO 3166-1 alpha-2)."""

    count: int
    """Number of countries."""


class DetectCountryResponse(BaseModel):
    """Response from ``GET /v1/signpost/detect-country``.

    The route reads the geo headers a proxy injects (``cf-ipcountry``,
    ``x-country``, ``x-vercel-ip-country``, ``cf-region-code``, ``cf-region``).
    A direct call to api.nope.net carries none of them and returns the miss
    shape with HTTP 200. Key on ``country_code`` (or ``detected``);
    ``country_name`` is empty for countries outside the API's 36-entry name map.
    """

    model_config = {"extra": "allow"}

    country_code: str
    """Detected country code, or an empty string on a miss."""

    country_name: str
    """Human-readable country name, or an empty string."""

    subdivision_code: Optional[str] = None
    """ISO 3166-2 subdivision (e.g. 'US-CA') when the proxy sent a region."""

    subdivision_name: Optional[str] = None
    """Human-readable region name when the proxy sent one."""

    error: Optional[str] = None
    """Set on a miss."""

    @property
    def detected(self) -> bool:
        """True when ``country_code`` is non-empty."""
        return self.country_code != ""

    def __repr_args__(self) -> Iterator[Tuple[Optional[str], Any]]:
        # A property is absent from pydantic's default repr, so a miss printed
        # as country_code='' with no sign of the derived flag. Shown last; it is
        # still not a field and never reaches model_dump().
        yield from super().__repr_args__()
        yield "detected", self.detected


class SignpostConfig(BaseModel):
    """Filters for the basic ``signpost`` lookup.

    Scopes and populations must come from the generated vocabularies
    (``nope_net.SERVICE_SCOPES``, ``nope_net.POPULATIONS``); the API returns
    400 with ``invalid_scopes`` otherwise.
    """

    scopes: Optional[List[ServiceScope]] = None
    """Service scopes to filter by (e.g. 'suicide', 'domestic_violence')."""

    populations: Optional[List[Population]] = None
    """Populations to filter by (e.g. 'youth', 'veterans', 'lgbtq')."""

    subdivisions: Optional[List[str]] = None
    """ISO 3166-2 subdivisions within the country (e.g. 'GB-SCT')."""

    limit: Optional[int] = None
    """Maximum number of resources to return (the API clamps to 10)."""

    urgent: Optional[bool] = None
    """Ranking hint. Places 24/7 resources first among ties on relevance and
    priority tier without filtering other matches."""


class SignpostSmartConfig(BaseModel):
    """Filters for ``signpost_smart``. The ranker returns at most 5 picks."""

    scopes: Optional[List[ServiceScope]] = None
    """Service scopes to filter the candidate pool by."""

    populations: Optional[List[Population]] = None
    """Populations to filter the candidate pool by."""

    limit: Optional[int] = None
    """Maximum picks (up to 5)."""


# Deprecated names kept for the /v1/resources/* twins (sunset 2027-01-01).
ResourcesConfig = SignpostConfig
ResourcesResponse = SignpostResponse
ResourcesSmartResponse = SignpostSmartResponse
ResourceByIdResponse = SignpostByIdResponse
ResourcesCountriesResponse = SignpostCountriesResponse


# =============================================================================
# Oversight types (/v1/oversight/*)
# =============================================================================

# Concern level for AI behavior analysis
ConcernLevel = Literal["none", "low", "medium", "high", "critical"]

# Trajectory of concern within a conversation
Trajectory = Literal["improving", "stable", "worsening"]

# Behavior severity in Oversight analysis
OversightSeverity = Literal["low", "medium", "high", "critical"]

# Human indicator types observed in conversation
HumanIndicatorType = Literal[
    "distress_markers", "acquiescence", "disengagement", "escalation", "pushback"
]

# Analysis strategy: one pass, or sliding windows for long conversations
OversightAnalysisStrategy = Literal["single", "sliding"]

# Analysis mode: full (default) or fast screening
OversightAnalysisMode = Literal["full", "fast"]


class OversightMessage(BaseModel):
    """A message in an Oversight conversation."""

    model_config = {"extra": "allow"}

    role: Literal["user", "assistant", "system"]
    """Message role."""

    content: str
    """Message content."""

    message_id: Optional[str] = None
    """Customer-provided unique identifier for this message/turn."""

    timestamp: Optional[str] = None
    """When this message was sent (ISO 8601)."""

    agent_id: Optional[str] = None
    """Agent/bot identifier that generated this message (for assistant messages)."""

    agent_version: Optional[str] = None
    """Agent version string."""

    context: Optional[str] = None
    """Retrieved RAG/memory context that informed this response."""


class OversightConversationMetadata(BaseModel):
    """Metadata about an Oversight conversation."""

    model_config = {"extra": "allow"}

    user_id_hash: Optional[str] = None
    """Hashed identifier for the end-user (for cross-session trajectory tracking)."""

    session_id: Optional[str] = None
    """Customer's session identifier."""

    session_number: Optional[int] = None
    """Session number for this user (1, 2, 3...)."""

    user_is_minor: Optional[bool] = None
    """Whether the end-user is a minor (escalates all severity levels)."""

    user_age_bracket: Optional[Literal["child", "teen", "adult", "unknown"]] = None
    """Age bracket of the end-user."""

    platform: Optional[str] = None
    """Platform where conversation occurred (e.g., "ios", "web", "discord")."""

    product: Optional[str] = None
    """Product/bot name."""

    started_at: Optional[str] = None
    """When the conversation started (ISO 8601)."""

    ended_at: Optional[str] = None
    """When the conversation ended (ISO 8601)."""

    tags: Optional[List[str]] = None
    """Customer-defined tags for categorization."""

    bot_context: Optional[str] = None
    """Free-form description of the bot or persona. The ``bot_context`` argument
    of ``oversight_analyze`` is merged here server-side and reaches the analysis
    prompt as a calibration block."""


class OversightConversation(BaseModel):
    """A conversation to analyze with Oversight."""

    model_config = {"extra": "allow"}

    conversation_id: Optional[str] = None
    """Unique identifier for the conversation (required for ingest)."""

    messages: List[OversightMessage]
    """Messages in the conversation."""

    metadata: Optional[OversightConversationMetadata] = None
    """Optional metadata about the conversation."""


class OversightBehaviorFilter(BaseModel):
    """Request-side filter on which behaviours the result includes.

    Filtering happens after analysis, so the model still sees the full taxonomy.
    ``enabled`` and ``disabled`` are exclusive when both are non-empty.
    """

    enabled: Optional[List[OversightBehaviorCode]] = None
    """Only include these behaviour codes (allowlist)."""

    disabled: Optional[List[OversightBehaviorCode]] = None
    """Exclude these behaviour codes (blocklist)."""

    min_severity: Optional[OversightSeverity] = None
    """Only include behaviours at or above this severity."""

    categories: Optional[List[OversightBehaviorCategory]] = None
    """Only include behaviours from these categories."""


class OversightAppliedFilter(BaseModel):
    """The filter the API applied, echoed on the result as ``filter_applied``.

    Codes are plain strings here so a taxonomy addition on the API never
    breaks parsing.
    """

    model_config = {"extra": "allow"}

    enabled: Optional[List[str]] = None
    disabled: Optional[List[str]] = None
    min_severity: Optional[OversightSeverity] = None
    categories: Optional[List[str]] = None


class OversightAnalyzeConfig(BaseModel):
    """Configuration for an Oversight analyze request."""

    strategy: Optional[OversightAnalysisStrategy] = None
    """Force a strategy. Auto-selected from conversation length when omitted
    (sliding at 50 messages or more). Ignored by the demo route."""

    mode: Optional[OversightAnalysisMode] = None
    """``full`` (default) or ``fast``. Fast mode uses a quicker model, returns no
    ``summary``/``pattern_assessment``, an empty ``turn_analysis`` and the constant
    trajectory ``stable``."""

    include_raw_xml: Optional[bool] = None
    """Include the raw model XML in the response (debugging)."""

    model: Optional[str] = None
    """Custom model to use. Ignored by the demo route."""


class DetectedBehavior(BaseModel):
    """A detected behavior in the conversation."""

    model_config = {"extra": "allow"}

    code: str
    """Behavior code (e.g., 'validation_of_suicidal_ideation', 'romantic_escalation')."""

    severity: OversightSeverity
    """Severity of this behavior instance."""

    turn_number: int
    """Assistant turn where the behavior was detected (1-based)."""

    evidence: str
    """Evidence quote from the conversation."""

    reasoning: str
    """Reasoning for why this behavior was flagged."""


class AggregatedBehavior(BaseModel):
    """Aggregated behavior for summary (multiple instances collapsed)."""

    model_config = {"extra": "allow"}

    code: str
    """Behavior code."""

    severity: OversightSeverity
    """Highest severity across instances."""

    turn_count: int
    """Number of turns where this behavior appeared (always 1 in fast mode)."""

    recommendation: Optional[str] = None
    """Actionable recommendation for correcting this behavior."""


class TurnAnalysis(BaseModel):
    """Turn-level analysis."""

    model_config = {"extra": "allow"}

    turn_number: int
    """Assistant turn number (1-based)."""

    role: Literal["assistant"]
    """Role of this turn (always 'assistant')."""

    content_summary: str
    """Brief summary of turn content."""

    behaviors: List[DetectedBehavior]
    """Behaviors detected in this turn."""

    missed_intervention: bool
    """Whether the AI missed an opportunity to intervene."""


class HumanIndicator(BaseModel):
    """Human response indicator."""

    model_config = {"extra": "allow"}

    type: HumanIndicatorType
    """Type of indicator."""

    observation: str
    """What was observed."""

    turns: List[int]
    """Turn numbers where this was observed (1-based)."""


class OversightMessageRange(BaseModel):
    """Exact 0-indexed message slice a window analysed."""

    model_config = {"extra": "allow"}

    start_index: int
    end_index_exclusive: int


class OversightConversationTurnRange(BaseModel):
    """1-indexed conversation turn range a window represents."""

    model_config = {"extra": "allow"}

    start_turn: int
    end_turn: int


class OversightWindow(BaseModel):
    """Which messages a window covered.

    ``start_turn``/``end_turn`` are the legacy names (message indexes, end
    exclusive); prefer ``message_range`` and ``conversation_turn_range``.
    """

    model_config = {"extra": "allow"}

    start_turn: int
    end_turn: int
    message_range: Optional[OversightMessageRange] = None
    conversation_turn_range: Optional[OversightConversationTurnRange] = None


class WindowAnalysis(BaseModel):
    """Analysis of one window of a sliding-strategy run."""

    model_config = {"extra": "allow"}

    window: OversightWindow
    concern: ConcernLevel
    behaviors: List[DetectedBehavior]
    turn_analysis: List[TurnAnalysis]
    human_indicators: List[HumanIndicator]
    summary: str


class InflectionPoint(BaseModel):
    """A point where the concern level changed between consecutive windows."""

    model_config = {"extra": "allow"}

    turn: int
    """Conversation turn (1-based) where the change occurred."""

    concern_before: ConcernLevel
    concern_after: ConcernLevel
    trigger_behaviors: List[str]
    """Behaviors that appeared in the new window."""


class OversightAnalysisResult(BaseModel):
    """Result from Oversight analysis.

    Fast mode (``config.mode = "fast"``) omits ``summary`` and
    ``pattern_assessment``, returns ``turn_analysis`` and ``human_indicators``
    empty, ``conversation_summary`` as ``""`` and ``trajectory`` as the constant
    ``stable``. The sliding strategy adds ``windows``, ``concern_progression``,
    ``peak_concern`` and ``final_concern``.
    """

    model_config = {"extra": "allow", "protected_namespaces": ()}

    conversation_id: str
    """Conversation identifier."""

    analyzed_at: str
    """When analysis was performed (ISO 8601)."""

    conversation_summary: str
    """Brief summary of the conversation (empty in fast mode)."""

    overall_concern: ConcernLevel
    """Overall concern level."""

    trajectory: Trajectory
    """Trajectory of concern within the conversation (always ``stable`` in fast mode)."""

    summary: Optional[str] = None
    """Human-readable summary of findings. Absent in fast mode."""

    turn_analysis: List[TurnAnalysis]
    """Turn-by-turn analysis (assistant turns only; empty in fast mode)."""

    human_indicators: List[HumanIndicator]
    """Human response indicators observed."""

    pattern_assessment: Optional[str] = None
    """Pattern assessment narrative. Absent in fast mode."""

    detected_behaviors: List[AggregatedBehavior]
    """Aggregated behaviors (deduplicated across turns)."""

    model_used: Optional[str] = None
    """Model used for analysis."""

    latency_ms: Optional[int] = None
    """Analysis latency in milliseconds."""

    mode_used: Optional[OversightAnalysisMode] = None
    """Which analysis mode ran."""

    filter_applied: Optional[OversightAppliedFilter] = None
    """The behaviour filter that was applied, if any."""

    windows: Optional[List[WindowAnalysis]] = None
    """Per-window analyses (sliding strategy)."""

    concern_progression: Optional[List[ConcernLevel]] = None
    """Concern level per window, in order (sliding strategy)."""

    peak_concern: Optional[ConcernLevel] = None
    """Highest window concern (sliding strategy)."""

    final_concern: Optional[ConcernLevel] = None
    """Last window concern (sliding strategy)."""

    inflection_points: Optional[List[InflectionPoint]] = None
    """Where concern changed between windows."""

    context_for_next_window: Optional[str] = None
    """Context summary carried between windows."""

    narrative_summary: Optional[str] = None
    """Narrative summary for cross-session aggregation."""

    prompt_tokens: Optional[int] = None
    """Prompt tokens used."""

    completion_tokens: Optional[int] = None
    """Completion tokens used."""

    raw_xml: Optional[str] = None
    """Raw XML output (only if requested)."""


class OversightAnalyzeResponse(BaseModel):
    """Response from ``POST /v1/oversight/analyze`` (authenticated)."""

    model_config = {"extra": "allow"}

    result: OversightAnalysisResult
    """Analysis result."""

    strategy: OversightAnalysisStrategy
    """Which strategy was used."""

    strategy_reason: str
    """Why this strategy was chosen."""


class OversightDemoAnalyzeResponse(BaseModel):
    """Response from ``POST /v1/try/oversight/analyze`` (demo mode).

    The demo route ignores ``config.strategy`` and ``config.model``, keeps only
    ``role`` and ``content`` of each message, and caps input at 20 messages of
    10,000 characters.
    """

    model_config = {"extra": "allow"}

    mode: Literal["single", "fast"]
    """``fast`` when ``config.mode`` was fast, else ``single``."""

    result: OversightAnalysisResult
    """Analysis result."""

    try_endpoint: Literal[True]
    """Always true on the demo route."""


class OversightIngestConfig(BaseModel):
    """Configuration for an Oversight ingest request."""

    model: Optional[str] = None
    """Custom model to use."""


class TruncationWarning(BaseModel):
    """What ingest changed about a conversation before analysis."""

    model_config = {"extra": "allow"}

    type: Literal["message_scaffolded", "message_truncated", "conversation_truncated"]
    """Warning type."""

    details: str
    """What was modified."""


class OversightIngestConversationResult(BaseModel):
    """Per-conversation result from ingest."""

    model_config = {"extra": "allow"}

    conversation_id: str
    """Conversation ID."""

    overall_concern: ConcernLevel
    """Overall concern level."""

    behaviors_detected: int
    """Number of behaviors detected."""

    truncation_warnings: Optional[List[TruncationWarning]] = None
    """Truncation warnings if the conversation was modified."""


class OversightIngestError(BaseModel):
    """Per-conversation error from ingest."""

    model_config = {"extra": "allow"}

    conversation_id: str
    """Conversation ID."""

    error: str
    """Error message."""


class OversightIngestResponse(BaseModel):
    """Response from ``POST /v1/oversight/ingest``.

    Ingest is synchronous today: ``status`` is ``complete`` or ``failed`` when
    the call returns, ``estimated_completion`` is never set and there is no
    polling route. The ``queued``/``processing`` values are kept for forward
    compatibility.
    """

    model_config = {"extra": "allow"}

    ingestion_id: str
    """Unique ingestion ID for tracking."""

    status: Literal["queued", "processing", "complete", "failed"]
    """Current status."""

    conversations_received: int
    """Number of conversations received."""

    conversations_processed: int
    """Number of conversations successfully processed."""

    estimated_completion: Optional[str] = None
    """Reserved; not set by the current synchronous route."""

    dashboard_url: str
    """URL to view results in dashboard."""

    results: Optional[List[OversightIngestConversationResult]] = None
    """Per-conversation results (present when at least one succeeded)."""

    errors: Optional[List[OversightIngestError]] = None
    """Per-conversation errors (present when at least one failed)."""


# =============================================================================
# Ocular (behavioral risk assessment, /v1/ocular)
# =============================================================================
#
# The customer-facing /v1/ocular response models the post-filter surface the
# gateway emits (api/lib/ocular-public-via-gex44/filter.ts). Head-code
# identifiers are stripped there; the demo route (/v1/try/ocular) adds them
# back under public family names.

# Per-axis level (also used for imminence). Exactly these five values.
OcularLevel = Literal["critical", "high", "moderate", "low", "minimal"]

# Arc phases reported in trajectory_shape.phases
OcularPhase = Literal["baseline", "emerging", "escalating", "de-escalating", "crisis"]

OcularThoroughness = Literal["fast", "auto", "thorough"]


class OcularAxis(BaseModel):
    """Per-axis output: a level plus the raw score in [0, 1]."""

    model_config = {"extra": "allow"}

    level: OcularLevel
    score: float


class OcularSignals(BaseModel):
    """Per-axis signal groups: 8 user-risk axes and 4 AI-behavior axes.

    user axes: suicide, self_harm, harm_to_others, abuse, sexual_violence,
    exploitation, stalking, self_neglect.

    ai axes: harm_provision, emotional_failure, manipulation,
    safeguarding_failure (populated when assistant turns are present).
    """

    model_config = {"extra": "allow"}

    user: Dict[str, OcularAxis] = Field(default_factory=dict)
    ai: Dict[str, OcularAxis] = Field(default_factory=dict)


class OcularStability(BaseModel):
    """Per-axis stability scores in [0, 1]; higher means more confident.

    Same nesting as ``signals`` plus a top-level ``imminence``. Present only
    when Ocular ran several variants (``thoroughness="thorough"``); otherwise
    the response carries ``stability: null``.
    """

    model_config = {"extra": "allow"}

    user: Dict[str, float] = Field(default_factory=dict)
    ai: Dict[str, float] = Field(default_factory=dict)
    imminence: float = 0.0


class OcularTrajectoryEntry(BaseModel):
    """One scored turn of ``trajectory`` (requested with ``per_turn=True``).

    ``salience`` is the same continuous score as the top-level field computed
    for that turn. ``signals_by_axis`` carries the per-axis intensities for the
    public axis vocabulary (user axes bare, AI axes ``ai_``-prefixed, plus the
    ``fiction``/``genuine`` context scalars) so a caller can see which turn
    carried which risk.
    """

    model_config = {"extra": "allow"}

    role: str
    """``user`` or ``assistant`` (the gateway normalises the upstream ``ai``)."""

    turn: int
    """0-based position of this message in the request's ``messages``. With
    the default ``trajectory_stride`` of 3 only every third turn counting back
    from the last is scored, so consecutive entries can be three apart."""

    salience: float
    """The continuous score computed for this turn alone."""

    signals_by_axis: Optional[Dict[str, float]] = None
    """Per-axis intensities keyed ``suicide``, ``self_harm``, ... for the user
    axes, ``ai_manipulation``, ``ai_harm_provision``, ... for the AI axes, plus
    the ``genuine`` and ``fiction`` context scalars."""


class OcularTrajectoryShape(BaseModel):
    """Arc summary of the trajectory.

    Present on ``/v1/ocular`` whenever at least one turn was scored; the demo
    route never sends it. Two indexings are in play: ``onsets`` is keyed by
    turn index (the ``turn`` values in ``trajectory``), while ``phases``,
    ``slopes`` and ``peak_turn`` index the ``trajectory`` list itself, so with
    one scored turn ``peak_turn`` is 0 even when that entry's ``turn`` is 2.
    ``phases``, ``slopes``, ``peak_turn`` and ``peak_crisis`` track the crisis
    (suicide) axis. ``onsets`` spans every public axis. A field is absent when
    the upstream did not compute it.
    """

    model_config = {"extra": "allow"}

    onsets: Optional[Dict[str, int]] = None
    """Axis -> turn index (as in ``trajectory[].turn``) where that axis first
    crossed its onset threshold."""

    phases: Optional[List[OcularPhase]] = None
    """Phase label per scored turn, aligned with ``trajectory``."""

    slopes: Optional[List[float]] = None
    """Crisis-axis slope per scored turn (delta against the previous scored
    turn), aligned with ``trajectory``."""

    peak_turn: Optional[int] = None
    """Index into ``trajectory`` of the entry with the highest crisis-axis
    signal (a list position, not a ``turn`` value)."""

    peak_crisis: Optional[float] = None
    """Highest crisis-axis signal across the scored turns."""


class OcularMeta(BaseModel):
    """Response metadata.

    ``version`` is the Ocular model build identifier. The gateway forwards
    ``windowed`` and ``windows`` whenever the upstream sets them, which the
    current build always does (``false`` and ``1`` for un-windowed input);
    ``truncated`` appears when the input was cut at the gateway.
    """

    model_config = {"extra": "allow"}

    version: str
    inference_ms: int
    windowed: Optional[bool] = None
    windows: Optional[int] = None
    truncated: Optional[bool] = None


class OcularResponse(BaseModel):
    """Response from ``POST /v1/ocular`` ($0.0001 per call).

    The customer decision surface is the continuous ``salience`` score in
    [0, 1] plus the structural axes under ``signals.user.*`` (8 axes) and
    ``signals.ai.*`` (4 axes). Pick the threshold that fits your downstream
    action; published guidance uses T_WATCH=0.30 and T_DANGER=0.60 as
    reference cutoffs (see ``docs.nope.net/ocular``).

    ``subject`` ("self" / "other" / "unknown") identifies who the speaker-side
    risk pertains to; ``imminence`` is a separate axis. ``fiction`` and
    ``authenticity`` are context modulators already factored into ``salience``
    and per-axis levels server-side; surface them for inspection.

    ``trajectory`` and ``trajectory_shape`` are present only when the request
    set ``per_turn=True``; the shape follows whenever at least one turn was
    scored (see :class:`OcularTrajectoryShape` for its two indexings).
    """

    model_config = {"extra": "allow"}

    salience: float
    """Continuous severity score in [0, 1]. The customer decision contract."""

    subject: str
    """Who the speaker-side risk pertains to: 'self' / 'other' / 'unknown'."""

    imminence: OcularAxis
    """How urgent the concern is (its own axis, outside ``signals``)."""

    fiction: float
    """Roleplay/fiction-framing strength in [0, 1] (informational)."""

    authenticity: float
    """Authenticity-of-distress signal in [0, 1] (informational)."""

    signals: OcularSignals
    """8 user-risk axes and 4 AI-behavior axes, each with level and score."""

    thoroughness: OcularThoroughness
    """Which ensemble depth the call ran at."""

    confidence: Optional[float] = None
    """Aggregate confidence in [0, 1] across the variants produced (null when single-variant)."""

    stability: Optional[OcularStability] = None
    """Per-axis stability across variants; null when single-variant."""

    meta: OcularMeta
    """Response metadata: model version, inference time, windowing flags."""

    trajectory: Optional[List[OcularTrajectoryEntry]] = None
    """Scored turns in turn order. Only with ``per_turn=True``; with the default
    ``trajectory_stride`` of 3 only every third turn counting back from the
    last is included."""

    trajectory_shape: Optional[OcularTrajectoryShape] = None
    """Arc summary of the trajectory. Only with ``per_turn=True`` on
    ``/v1/ocular``; the demo route never sends it."""


class OcularHead(BaseModel):
    """A screening head on the demo wire, keyed by its public family name."""

    model_config = {"extra": "allow"}

    code: str
    score: float


class OcularDemoDetail(BaseModel):
    """Per-head scores on the demo wire (public family names)."""

    model_config = {"extra": "allow"}

    scores: Dict[str, float]
    calibrated: Dict[str, float]


class OcularDemoResponse(OcularResponse):
    """Response from ``POST /v1/try/ocular`` (demo mode).

    Same surface as :class:`OcularResponse` plus ``heads`` and ``detail``,
    both keyed by public family head names (``USER_SUICIDE_HEAD_A`` ...). The
    demo route caps input at 12 messages of 4,000 characters, returns
    ``trajectory`` with ``per_turn=True`` but never ``trajectory_shape``, and
    ignores ``thoroughness`` and the identity fields.
    """

    heads: List[OcularHead]
    detail: OcularDemoDetail


# =============================================================================
# Signpost search (vector semantic search, GET /v1/signpost/search)
# =============================================================================


class SignpostSearchContact(BaseModel):
    """One contact method on a search row, as the directory stores it.

    Only ``type`` is always present. The live wire mixes ``{type, value}``,
    ``{type, url}`` (chat contacts), ``{label, type, value}`` and tiered rows
    with ``source`` and ``confidence`` (fixture
    ``signpost/search.auth.mixed-contacts.json``).
    """

    model_config = {"extra": "allow"}

    type: str
    """Contact type (phone, email, chat, sms, ...)."""

    value: Optional[str] = None
    """Number or address; chat contacts carry ``url`` instead."""

    url: Optional[str] = None
    """URL for chat and web contacts."""

    label: Optional[str] = None
    """Display label, when the directory has one."""

    tier: Optional[Union[int, str]] = None
    """Contact tier (``"1"`` is primary); absent on untiered rows."""

    source: Optional[str] = None
    """Where the contact was verified."""


class SignpostSearchResult(BaseModel):
    """A single semantic-search hit.

    Search returns the raw directory row (plural ``service_scopes``,
    ``populations``, ``resource_type``, ``contacts``, explicit nulls) with the
    tier-1 contacts flattened to top-level keys and ``type`` mirroring
    ``resource_type``. It is a different shape from :class:`CrisisResource`.
    """

    model_config = {"extra": "allow"}

    id: str
    """Directory UUID; usable with ``signpost_by_id``."""

    name: str
    name_local: Optional[str] = None
    country_code: str
    subdivision_code: Optional[str] = None
    country_codes: List[str]
    subdivision_codes: List[str]
    service_scopes: List[str]
    populations: List[str]
    description: Optional[str] = None
    resource_type: str
    contacts: List[SignpostSearchContact]
    website_url: Optional[str] = None
    is_24_7: bool
    availability: Optional[str] = None
    timezone: Optional[str] = None
    opening_hours_osm: Optional[str] = None
    hours_confidence: Optional[str] = None
    languages: List[str]
    similarity: float
    """Vector similarity to the query in [0, 1]; higher is more relevant."""

    phone: Optional[str] = None
    """Flattened tier-1 phone contact."""

    sms_number: Optional[str] = None
    chat_url: Optional[str] = None
    whatsapp_url: Optional[str] = None
    email: Optional[str] = None
    line_url: Optional[str] = None
    telegram_url: Optional[str] = None
    wechat_id: Optional[str] = None
    type: CrisisResourceType
    """Same value as ``resource_type``."""

    open_status: OpenStatus
    """Computed open/closed status."""


class SignpostSearchTiming(BaseModel):
    """Timing breakdown for a semantic search."""

    model_config = {"extra": "allow"}

    embed_ms: float
    """Time spent embedding the query (ms)."""

    search_ms: float
    """Time spent on the vector search (ms)."""

    total_ms: float
    """Total time (embed + search) (ms)."""


class SignpostSearchResponse(BaseModel):
    """Response from ``GET /v1/signpost/search``."""

    model_config = {"extra": "allow"}

    query: str
    """The search query that was run."""

    country: Optional[str] = None
    """Country filter applied, or None when unfiltered."""

    results: List[SignpostSearchResult]
    """Resources ranked by semantic similarity to the query."""

    count: int
    """Number of results returned."""

    timing: Optional[SignpostSearchTiming] = None
    """Timing breakdown for the search."""


# =============================================================================
# Billing (/v1/billing/*). Amounts are mills: 1 mill = $0.001.
# =============================================================================


class BillingTopupHistoryEntry(BaseModel):
    """A past top-up."""

    model_config = {"extra": "allow"}

    id: str
    amount_mills: float
    amount_formatted: str
    status: str
    created_at: str
    completed_at: Optional[str] = None


class BillingTopupOption(BaseModel):
    """A purchasable top-up amount with the calls it buys."""

    model_config = {"extra": "allow"}

    id: str
    amount_mills: float
    label: str
    evaluates: int
    resources_smart: int
    screens: int
    """Screens this amount buys."""


class BillingBalanceResponse(BaseModel):
    """``GET /v1/billing/balance``."""

    model_config = {"extra": "allow"}

    balance_mills: float
    balance_formatted: str
    estimated_evaluates: int
    estimated_resources_smart: int
    estimated_screens: int
    """Screens the balance covers."""
    low_balance: bool
    topup_history: List[BillingTopupHistoryEntry]
    topup_options: List[BillingTopupOption]


class BillingUsageBreakdownEntry(BaseModel):
    """Spend for one endpoint over the period."""

    model_config = {"extra": "allow"}

    endpoint: str
    calls: int
    cost_mills: float
    cost_formatted: str
    referrals: int


class BillingUsageResponse(BaseModel):
    """``GET /v1/billing/usage``."""

    model_config = {"extra": "allow"}

    period_start: str
    period_end: Optional[str] = None
    total_spend_mills: float
    total_spend_formatted: str
    breakdown: List[BillingUsageBreakdownEntry]


class BillingUsageRecord(BaseModel):
    """One billed call."""

    model_config = {"extra": "allow"}

    id: str
    endpoint: str
    cost_mills: float
    cost_formatted: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: str


class BillingUsageHistoryResponse(BaseModel):
    """``GET /v1/billing/usage/history``."""

    model_config = {"extra": "allow"}

    records: List[BillingUsageRecord]
    total: int
    limit: int
    offset: int


class BillingPricingEntry(BaseModel):
    """Price of one endpoint."""

    model_config = {"extra": "allow"}

    cost_mills: float
    cost_display: str
    description: Optional[str] = None


class BillingPricingResponse(BaseModel):
    """``GET /v1/billing/pricing`` (public).

    ``pricing`` is keyed by endpoint name (``evaluate``, ``ocular``,
    ``signpost_smart``, ``resources_smart``, ``oversight_analyze``,
    ``oversight_ingest``, ``v0_screen``, ``screen``, ``v0_evaluate``,
    ``resources``); unknown keys are kept.
    """

    model_config = {"extra": "allow"}

    unit: str
    unit_description: str
    pricing: Dict[str, BillingPricingEntry]
    topup_options: List[BillingTopupOption]
    free_credit_mills: float
    free_credit_display: str


class BillingTopupResponse(BaseModel):
    """``POST /v1/billing/topup``: a Stripe Checkout URL."""

    model_config = {"extra": "allow"}

    checkout_url: str
