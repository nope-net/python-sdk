"""
NOPE SDK types (v1 API)

Pydantic models for requests and responses. Response models tolerate unknown
keys (``extra="allow"``) so an additive API change never breaks parsing; the
contract tests under ``tests/contract/`` pin every shape to a live capture.

Risks separate WHO is at risk (``subject``) from WHAT kind of harm (``type``).
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

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

    These four keys are the whole of what ``/v1/evaluate`` reads. In demo mode
    the client also sends ``user_country`` mirroring ``country`` because the
    ``/v1/try/evaluate`` route reads that key (API fix A-1 pending).
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
    """Directory UUID. Carried by search results today; the basic and smart
    routes gain it with API fix A-6."""

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
# Resources Types (for /v1/resources/* endpoints)
# =============================================================================


class RankedResource(BaseModel):
    """A resource with LLM-computed relevance ranking."""

    model_config = {"extra": "allow"}

    resource: CrisisResource
    """The crisis resource."""

    why: str
    """Brief explanation of why this resource is relevant (1-2 sentences)."""

    rank: int
    """Rank position (1 = most relevant)."""


class ResourcesResponse(BaseModel):
    """Response from GET /v1/resources endpoint."""

    model_config = {"extra": "allow"}

    country: str
    """Country code (ISO 3166-1 alpha-2)."""

    resources: List[CrisisResource]
    """List of crisis resources."""

    count: int
    """Number of resources returned."""

    primary: Optional[List[CrisisResource]] = None
    """Primary resources matching requested scopes (when scopes provided)."""

    secondary: Optional[List[CrisisResource]] = None
    """Secondary general resources (when scopes provided)."""

    scopes_requested: Optional[List[str]] = None
    """Scopes that were requested (when provided)."""


class ResourcesSmartResponse(BaseModel):
    """Response from GET /v1/resources/smart endpoint."""

    model_config = {"extra": "allow"}

    country: str
    """Country code (ISO 3166-1 alpha-2)."""

    query: str
    """The search query used."""

    ranked: List[RankedResource]
    """Resources ranked by relevance to query."""

    count: int
    """Number of resources returned."""

    scopes_requested: Optional[List[str]] = None
    """Scopes that were requested (when provided)."""


class ResourceByIdResponse(BaseModel):
    """Response from GET /v1/resources/:id endpoint."""

    model_config = {"extra": "allow"}

    resource: CrisisResource
    """The requested crisis resource."""


class ResourcesCountriesResponse(BaseModel):
    """Response from GET /v1/resources/countries endpoint."""

    model_config = {"extra": "allow"}

    countries: List[str]
    """List of supported country codes (ISO 3166-1 alpha-2)."""

    count: int
    """Number of countries."""


class DetectCountryResponse(BaseModel):
    """Response from GET /v1/resources/detect-country endpoint."""

    model_config = {"extra": "allow"}

    country_code: str
    """Detected country code (ISO 3166-1 alpha-2), or empty string if not detected."""

    country_name: str
    """Human-readable country name, or empty string if not detected."""

    error: Optional[str] = None
    """Error message if country could not be detected."""


class ResourcesConfig(BaseModel):
    """Configuration for resources request."""

    scopes: Optional[List[str]] = None
    """Service scopes to filter by (e.g., 'suicide_prevention', 'domestic_violence')."""

    populations: Optional[List[str]] = None
    """Populations to filter by (e.g., 'youth', 'veterans', 'lgbtq')."""

    limit: Optional[int] = None
    """Maximum number of resources to return (max 10)."""

    urgent: Optional[bool] = None
    """Only return 24/7 urgent resources."""


# =============================================================================
# Oversight Types (for /v1/oversight/* endpoints)
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

# Analysis strategy
OversightAnalysisStrategy = Literal["single", "sliding"]


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


class OversightConversation(BaseModel):
    """A conversation to analyze with Oversight."""

    model_config = {"extra": "allow"}

    conversation_id: Optional[str] = None
    """Unique identifier for the conversation."""

    messages: List[OversightMessage]
    """Messages in the conversation."""

    metadata: Optional[OversightConversationMetadata] = None
    """Optional metadata about the conversation."""


class DetectedBehavior(BaseModel):
    """A detected behavior in the conversation."""

    model_config = {"extra": "allow"}

    code: str
    """Behavior code (e.g., 'validation_of_suicidal_ideation', 'romantic_escalation')."""

    severity: OversightSeverity
    """Severity of this behavior instance."""

    turn_number: int
    """Turn number where behavior was detected (0-indexed)."""

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
    """Number of turns where this behavior appeared."""


class TurnAnalysis(BaseModel):
    """Turn-level analysis."""

    model_config = {"extra": "allow"}

    turn_number: int
    """Turn number (0-indexed)."""

    role: Literal["assistant"] = "assistant"
    """Role of this turn (always 'assistant' for analysis)."""

    content_summary: str
    """Brief summary of turn content."""

    behaviors: List[DetectedBehavior]
    """Behaviors detected in this turn."""

    missed_intervention: bool
    """Whether AI missed an opportunity to intervene."""


class HumanIndicator(BaseModel):
    """Human response indicator."""

    model_config = {"extra": "allow"}

    type: HumanIndicatorType
    """Type of indicator."""

    observation: str
    """What was observed."""

    turns: List[int]
    """Turn numbers where this was observed."""


class OversightAnalysisResult(BaseModel):
    """Result from Oversight analysis."""

    model_config = {"extra": "allow", "protected_namespaces": ()}

    conversation_id: str
    """Conversation identifier."""

    analyzed_at: str
    """When analysis was performed (ISO 8601)."""

    conversation_summary: str
    """Brief summary of the conversation."""

    overall_concern: ConcernLevel
    """Overall concern level."""

    trajectory: Trajectory
    """Trajectory of concern within the conversation."""

    summary: str
    """Human-readable summary of findings."""

    turn_analysis: List[TurnAnalysis]
    """Turn-by-turn analysis (assistant turns only)."""

    human_indicators: List[HumanIndicator]
    """Human response indicators observed."""

    pattern_assessment: str
    """Pattern assessment narrative."""

    detected_behaviors: List[AggregatedBehavior]
    """Aggregated behaviors (deduplicated across turns)."""

    model_used: str
    """Model used for analysis."""

    latency_ms: Optional[int] = None
    """Analysis latency in milliseconds."""

    prompt_tokens: Optional[int] = None
    """Prompt tokens used."""

    completion_tokens: Optional[int] = None
    """Completion tokens used."""

    raw_xml: Optional[str] = None
    """Raw XML output (only if requested)."""


class OversightAnalyzeConfig(BaseModel):
    """Configuration for Oversight analyze request."""

    strategy: Optional[OversightAnalysisStrategy] = None
    """Force a specific analysis strategy. If None, auto-selects based on conversation length."""

    include_raw_xml: Optional[bool] = None
    """Include raw XML in response (for debugging)."""

    model: Optional[str] = None
    """Custom model to use."""


class OversightAnalyzeResponse(BaseModel):
    """Response from /v1/oversight/analyze."""

    model_config = {"extra": "allow"}

    result: OversightAnalysisResult
    """Analysis result."""

    strategy: Optional[OversightAnalysisStrategy] = None
    """Which strategy was used (authenticated endpoint)."""

    strategy_reason: Optional[str] = None
    """Why this strategy was chosen (authenticated endpoint)."""

    mode: Optional[Literal["single", "windowed"]] = None
    """Analysis mode (demo endpoint)."""

    try_endpoint: Optional[bool] = None
    """Whether this came from try endpoint."""


class OversightIngestConfig(BaseModel):
    """Configuration for Oversight ingest request."""

    model: Optional[str] = None
    """Custom model to use."""


class TruncationWarning(BaseModel):
    """Truncation warning from ingest."""

    model_config = {"extra": "allow"}

    type: str
    """Warning type."""

    message: str
    """Warning message."""


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
    """Truncation warnings if conversation was modified."""


class OversightIngestError(BaseModel):
    """Per-conversation error from ingest."""

    model_config = {"extra": "allow"}

    conversation_id: str
    """Conversation ID."""

    error: str
    """Error message."""


class OversightIngestResponse(BaseModel):
    """Response from /v1/oversight/ingest."""

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
    """Estimated completion time (ISO 8601)."""

    dashboard_url: str
    """URL to view results in dashboard."""

    results: Optional[List[OversightIngestConversationResult]] = None
    """Per-conversation results (if complete)."""

    errors: Optional[List[OversightIngestError]] = None
    """Per-conversation errors (if any)."""


# =============================================================================
# Ocular (behavioral risk assessment — /v1/ocular)
# =============================================================================
#
# The customer-facing /v1/ocular response models the post-filter surface the
# gateway emits (see `OcularPublicResponse` in the API repo for the wire spec
# this mirrors). Individual head-code identifiers are stripped by the gateway
# and are not part of the SDK surface.


class OcularAxis(BaseModel):
    """Per-axis output — level enum + raw score in [0, 1].

    The `level` string is one of: minimal, low, moderate, high, critical
    (imminence may also return `not_applicable`). Forward-compatible with
    future levels via the enum being a free `str`.
    """

    model_config = {"extra": "allow"}

    level: str
    score: float


class OcularSignals(BaseModel):
    """Per-axis signal groups: 8 user-risk axes + 4 AI-behavior axes.

    user axes: suicide, self_harm, harm_to_others, abuse, sexual_violence,
    exploitation, stalking, self_neglect.

    ai axes: harm_provision, emotional_failure, manipulation,
    safeguarding_failure (populated when assistant turns are present).
    """

    model_config = {"extra": "allow"}

    user: Dict[str, OcularAxis] = Field(default_factory=dict)
    ai: Dict[str, OcularAxis] = Field(default_factory=dict)


class OcularStability(BaseModel):
    """Per-axis stability scores in [0, 1] — higher = more confident.

    Same nesting shape as `signals` plus a top-level `imminence`. Returned
    only when Ocular produced multiple variants on the call; otherwise the
    response carries `stability: null`.
    """

    model_config = {"extra": "allow"}

    user: Dict[str, float] = Field(default_factory=dict)
    ai: Dict[str, float] = Field(default_factory=dict)
    imminence: float = 0.0


class OcularTrajectoryEntry(BaseModel):
    """Per-turn entry — minimal surface, no head codes.

    `salience` is the same continuous score as the top-level field, computed
    per turn so callers can plot the conversation arc.
    """

    model_config = {"extra": "allow"}

    role: str
    turn: int
    salience: float


class OcularMeta(BaseModel):
    """Response metadata.

    `version` is the Ocular model build identifier. `windowed`/`windows`/
    `truncated` are present only when the input was windowed at the gateway.
    """

    model_config = {"extra": "allow"}

    version: str
    inference_ms: int
    windowed: Optional[bool] = None
    windows: Optional[int] = None
    truncated: Optional[bool] = None


class OcularResponse(BaseModel):
    """Response from POST /v1/ocular.

    The customer decision surface is the continuous `salience` score in
    [0, 1] plus the structural axes under `signals.user.*` (8 axes) and
    `signals.ai.*` (4 axes). Pick the threshold that fits your downstream
    action; published guidance uses T_WATCH=0.30 and T_DANGER=0.60 as
    reference cutoffs (see `docs.nope.net/ocular`).

    `subject` ("self" / "other" / "unknown") identifies who the speaker-side
    risk pertains to; `imminence` is a separate axis. `fiction` and
    `authenticity` are context modulators already factored into `salience`
    and per-axis levels server-side — surface them for inspection, not
    re-aggregation.

    `stability` is only populated when Ocular produced multiple variants
    on the call. `trajectory` is present when the input had ≥2 turns; each
    entry carries the per-turn salience for plotting.
    """

    model_config = {"extra": "allow"}

    salience: float
    """Continuous severity score in [0, 1]. The customer decision contract."""

    subject: str
    """Who the speaker-side risk pertains to — 'self' / 'other' / 'unknown'."""

    imminence: OcularAxis
    """How urgent the concern is (separate axis, not part of `signals`)."""

    fiction: float
    """Roleplay/fiction-framing strength in [0, 1] (informational)."""

    authenticity: float
    """Authenticity-of-distress signal in [0, 1] (informational)."""

    signals: OcularSignals
    """8 user-risk axes + 4 AI-behavior axes, each with level + score."""

    thoroughness: Literal["fast", "auto", "thorough"]
    """Which ensemble depth the call ran at."""

    confidence: Optional[float] = None
    """Aggregate confidence in [0, 1] across the variants produced (null when single-variant)."""

    stability: Optional[OcularStability] = None
    """Per-axis stability across variants — null when single-variant."""

    meta: OcularMeta
    """Response metadata: model version, inference time, windowing flags."""

    trajectory: Optional[List[OcularTrajectoryEntry]] = None
    """Per-turn salience trail when the input had ≥2 turns."""


# =============================================================================
# Signpost Search (vector semantic search — GET /v1/signpost/search)
# =============================================================================


class SignpostSearchResult(CrisisResource):
    """A single semantic-search hit.

    Carries all the flattened `CrisisResource` fields (the gateway lifts
    contact methods to the top level and computes `open_status`) plus the
    vector `similarity` score for this query.
    """

    model_config = {"extra": "allow"}

    id: Optional[str] = None
    """Database UUID of the resource."""

    similarity: Optional[float] = None
    """Vector similarity to the query in [0, 1]; higher = more relevant."""


class SignpostSearchTiming(BaseModel):
    """Timing breakdown for a semantic search."""

    model_config = {"extra": "allow"}

    embed_ms: float = 0.0
    """Time spent embedding the query (ms)."""

    search_ms: float = 0.0
    """Time spent on the vector search (ms)."""

    total_ms: float = 0.0
    """Total time (embed + search) (ms)."""


class SignpostSearchResponse(BaseModel):
    """Response from GET /v1/signpost/search."""

    model_config = {"extra": "allow"}

    query: str
    """The search query that was run."""

    country: Optional[str] = None
    """Country filter applied, or None when unfiltered."""

    results: List[SignpostSearchResult] = Field(default_factory=list)
    """Resources ranked by semantic similarity to the query."""

    count: int = 0
    """Number of results returned."""

    timing: Optional[SignpostSearchTiming] = None
    """Timing breakdown for the search."""
