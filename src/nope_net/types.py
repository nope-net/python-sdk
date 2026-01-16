"""
NOPE SDK Types (v1 API)

Pydantic models for API requests and responses.

Uses orthogonal subject/type separation:
- WHO is at risk (subject: self | other | unknown)
- WHAT type of harm (type: suicide | violence | abuse | ...)
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Core Enums / Literals
# =============================================================================

# Who is at risk
# - self: The speaker is at risk
# - other: Someone else is at risk (friend, family, stranger)
# - unknown: Ambiguous - classic "asking for a friend" territory
RiskSubject = Literal["self", "other", "unknown"]

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

# Communication style - how the user is expressing themselves
# Orthogonal to risk assessment - informs response style, not risk level.
CommunicationStyle = Literal[
    "direct",        # Explicit first-person ("I want to die")
    "humor",         # Dark humor, memes, "lol kms"
    "fiction",       # Creative writing, poetry, roleplay
    "hypothetical",  # "What if someone...", philosophical
    "distanced",     # "Asking for a friend", third-party framing
    "clinical",      # Professional/medical language
    "minimized",     # Hedged, softened ("not that I would, but...")
    "adversarial",   # Jailbreak attempts, encoded content
]

# Severity scale (how bad)
Severity = Literal["none", "mild", "moderate", "high", "critical"]

# Imminence scale (how soon)
Imminence = Literal["not_applicable", "chronic", "subacute", "urgent", "emergency"]

# Evidence grade for legal/clinical flags
EvidenceGrade = Literal["strong", "moderate", "weak", "consensus", "none"]

# Crisis resource type
CrisisResourceType = Literal[
    "emergency_number",
    "crisis_line",
    "text_line",
    "chat_service",
    "support_service",
    "reporting_portal",
    "online_resource",
]

# Crisis resource kind
CrisisResourceKind = Literal["helpline", "reporting_portal", "directory", "self_help_site"]

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
# Request Types
# =============================================================================


class Message(BaseModel):
    """A message in the conversation."""

    role: Literal["user", "assistant"]
    content: str
    timestamp: Optional[str] = None  # ISO 8601


class EvaluateConfig(BaseModel):
    """Configuration for evaluation request."""

    user_country: Optional[str] = None
    """User's country for crisis resources (ISO country code)."""

    locale: Optional[str] = None
    """Locale for language/region (e.g., 'en-US', 'es-MX')."""

    user_age_band: Optional[Literal["adult", "minor", "unknown"]] = None
    """User age band (affects response templates). Default: 'adult'."""

    policy_id: Optional[str] = None
    """Policy ID to use."""

    include_resources: Optional[bool] = None
    """Include crisis resources in response. Default: true."""

    return_assistant_reply: Optional[bool] = None
    """Whether to return a safe assistant reply."""

    assistant_safety_mode: Optional[Literal["template", "generate"]] = None
    """How to generate the recommended reply."""

    use_multiple_judges: Optional[bool] = None
    """Use multiple judges for higher confidence. Default: false."""

    models: Optional[List[str]] = None
    """Specify exact models to use (admin only)."""

    conversation_id: Optional[str] = None
    """Customer-provided conversation ID for webhook correlation."""

    end_user_id: Optional[str] = None
    """Customer-provided end-user ID for webhook correlation."""


class EvaluateRequest(BaseModel):
    """Request to /v1/evaluate endpoint."""

    messages: Optional[List[Message]] = None
    """Conversation messages. Either messages OR text must be provided."""

    text: Optional[str] = None
    """Plain text input. Either messages OR text must be provided."""

    config: EvaluateConfig = Field(default_factory=EvaluateConfig)
    """Configuration options."""

    user_context: Optional[str] = None
    """Free-text user context to help shape responses."""


# =============================================================================
# Risk Structure
# =============================================================================


class Risk(BaseModel):
    """
    A single identified risk.

    Each risk represents one subject + type combination with its assessment.
    A conversation can have multiple risks (e.g., IPV victim with suicidal ideation).
    """

    subject: RiskSubject
    """Who is at risk."""

    subject_confidence: float = Field(ge=0.0, le=1.0)
    """
    Confidence in subject determination (0.0-1.0).

    Low values indicate ambiguity:
    - 0.9+ = Clear ("I want to kill myself" → self)
    - 0.5-0.7 = Moderate ("Asking for a friend" → likely self, but uncertain)
    - <0.5 = Very uncertain
    """

    type: RiskType
    """What type of harm."""

    severity: Severity
    """How severe (none → critical)."""

    imminence: Imminence
    """How soon (not_applicable → emergency)."""

    confidence: float = Field(ge=0.0, le=1.0)
    """Confidence in this risk assessment (0.0-1.0)."""

    features: List[str]
    """Evidence features supporting this risk."""


# =============================================================================
# Communication Structure
# =============================================================================


class CommunicationStyleAssessment(BaseModel):
    """Communication style with confidence."""

    style: CommunicationStyle
    confidence: float = Field(ge=0.0, le=1.0)


class CommunicationAssessment(BaseModel):
    """Communication analysis."""

    styles: List[CommunicationStyleAssessment]
    """Detected communication styles (may have multiple)."""

    language: str
    """Detected language (ISO 639-1)."""

    locale: Optional[str] = None
    """Detected locale (e.g., 'en-US')."""


# =============================================================================
# Summary Structure
# =============================================================================


class Summary(BaseModel):
    """
    Quick summary derived from risks array.

    speaker_severity/imminence are calculated from risks where subject='self'
    and subject_confidence > 0.5. This ensures bystanders don't get
    crisis-level responses for third-party concerns.
    """

    speaker_severity: Severity
    """Max severity from risks where subject='self' and confidence > 0.5."""

    speaker_imminence: Imminence
    """Max imminence from risks where subject='self' and confidence > 0.5."""

    any_third_party_risk: bool
    """Whether any risk has subject='other'."""

    primary_concerns: str
    """Narrative summary of key findings."""


# =============================================================================
# Legal Flags
# =============================================================================


class IPVFlags(BaseModel):
    """
    IPV-specific flags.

    Based on DASH (UK) and Danger Assessment (Johns Hopkins).
    Strangulation is the single strongest predictor of homicide in IPV.
    """

    indicated: bool
    """IPV indicators present."""

    strangulation: bool
    """ANY history of strangulation/choking (750x homicide risk)."""

    lethality_risk: Literal["standard", "elevated", "severe", "extreme"]
    """Overall lethality risk."""

    escalation_pattern: Optional[bool] = None
    """Escalation pattern detected."""

    confidence: Optional[float] = None
    """Confidence in assessment."""


class SafeguardingConcernFlags(BaseModel):
    """
    Safeguarding concern flags.

    Indicates patterns that may trigger statutory obligations depending on
    jurisdiction and the platform's role. NOPE flags concerns; humans determine
    whether mandatory reporting applies based on local law and organizational policy.

    Note: AI systems are not mandatory reporters under any current statute.
    This flag surfaces patterns for human review, not legal determinations.
    """

    indicated: bool
    """Safeguarding concern indicators present."""

    context: Literal["minor_involved", "vulnerable_adult", "csa", "infant_at_risk", "elder_abuse"]
    """Context triggering the concern."""


class ThirdPartyThreatFlags(BaseModel):
    """Third-party threat flags (Tarasoff-style duty to warn)."""

    tarasoff_duty: bool
    """Tarasoff duty potentially triggered."""

    specific_target: bool
    """Specific identifiable target."""

    confidence: Optional[float] = None
    """Confidence in assessment."""


class StalkingFlags(BaseModel):
    """
    Stalking flags.

    Based on SAM (Stalking Assessment & Management) framework.
    Ex-intimate partner stalking has significantly elevated homicide risk.
    """

    ex_intimate_partner: bool
    """Former intimate partner (highest risk per SAM)."""

    escalation_detected: bool
    """Escalation in frequency/severity detected."""

    violence_history: bool
    """History of violence toward victim."""

    victim_fear_expressed: bool
    """Victim expresses fear for safety (predictive per SAM)."""

    risk_level: Literal["standard", "elevated", "severe"]
    """
    Risk level derived from SAM domains:
    - severe: violence_history + escalation, OR prior violence + victim fears for life
    - elevated: ex_intimate_partner, OR escalation + victim_fear
    - standard: Basic stalking pattern without amplifiers
    """


class LegalFlags(BaseModel):
    """
    Legal/safety flags.

    Derived from risks + features but surfaced separately for easy consumption.
    """

    ipv: Optional[IPVFlags] = None
    """Intimate partner violence indicators."""

    safeguarding_concern: Optional[SafeguardingConcernFlags] = None
    """Safeguarding concern indicators (patterns that may trigger statutory review)."""

    third_party_threat: Optional[ThirdPartyThreatFlags] = None
    """Third-party threat indicators."""

    stalking: Optional[StalkingFlags] = None
    """Stalking indicators (SAM-based)."""


# =============================================================================
# Protective Factors
# =============================================================================


class ProtectiveFactorsInfo(BaseModel):
    """Protective factors."""

    protective_factors: Optional[List[str]] = None
    """Specific protective factors present."""

    protective_factor_strength: Optional[Literal["weak", "moderate", "strong"]] = None
    """Overall strength assessment."""


# =============================================================================
# Filter Result
# =============================================================================


class PreliminaryRisk(BaseModel):
    """Preliminary risk from filter stage."""

    subject: RiskSubject
    type: RiskType
    confidence: float = Field(ge=0.0, le=1.0)


class FilterResult(BaseModel):
    """Filter stage results."""

    triage_level: Literal["none", "concern"]
    """Triage level."""

    preliminary_risks: List[PreliminaryRisk]
    """Preliminary risks detected (lightweight)."""

    reason: str
    """Reason for triage decision."""


# =============================================================================
# Crisis Resources
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
    """How confident we are in this status."""

    message: Optional[str] = None
    """Human-readable status message (e.g., 'Open 24/7', 'Closed · Opens in 2 hours')."""


class CrisisResource(BaseModel):
    """A crisis resource (helpline, text line, etc.)."""

    model_config = {"extra": "allow"}

    type: CrisisResourceType
    """Contact modality (how to reach them)."""

    name: str
    """Name of the resource/organization."""

    name_local: Optional[str] = None
    """Native script name (e.g., いのちの電話) for non-English resources."""

    phone: Optional[str] = None
    """Phone number."""

    text_instructions: Optional[str] = None
    """Text instructions (e.g., 'Text HOME to 741741') - human readable fallback."""

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
    """What the resource IS (helpline vs reporting portal vs directory)."""

    service_scope: Optional[List[str]] = None
    """Issues this resource handles (aligned with classification taxonomy)."""

    population_served: Optional[List[str]] = None
    """Populations this resource serves."""

    priority_tier: Optional[CrisisResourcePriorityTier] = None
    """Semantic priority for display and routing."""

    tags: Optional[List[str]] = None
    """Freeform tags for filtering/display."""

    prominence: Optional[ResourceProminence] = None
    """How well-known/established the resource is."""

    source: Optional[Literal["database", "web_search"]] = None
    """Source of this resource."""


# =============================================================================
# Response Types
# =============================================================================


class RecommendedReply(BaseModel):
    """Recommended reply content."""

    content: str
    source: Literal["template", "llm_generated"]
    notes: Optional[str] = None


class ResponseMetadata(BaseModel):
    """Metadata about the request/response."""

    model_config = {"extra": "allow"}

    access_level: Optional[Literal["unauthenticated", "authenticated", "admin"]] = None
    is_admin: Optional[bool] = None
    messages_truncated: Optional[bool] = None
    input_format: Optional[Literal["structured", "text_blob"]] = None
    api_version: Literal["v1"] = "v1"
    try_endpoint: Optional[bool] = None
    """True if request came via /v1/try/* endpoints."""


class EvaluateResponse(BaseModel):
    """Response from /v1/evaluate endpoint."""

    model_config = {"extra": "allow"}  # Allow extra fields from API

    request_id: str
    """Unique request ID for audit trail correlation."""

    timestamp: str
    """ISO 8601 timestamp for audit trail."""

    communication: CommunicationAssessment
    """Communication style analysis."""

    risks: List[Risk]
    """Identified risks (the core of v1)."""

    summary: Summary
    """Quick summary (derived from risks)."""

    legal_flags: Optional[LegalFlags] = None
    """Legal/safety flags."""

    protective_factors: Optional[ProtectiveFactorsInfo] = None
    """Protective factors."""

    confidence: float = Field(ge=0.0, le=1.0)
    """Overall confidence in assessment."""

    agreement: Optional[float] = None
    """Judge agreement (if multiple judges)."""

    crisis_resources: List[CrisisResource]
    """Crisis resources for user's region."""

    widget_url: Optional[str] = None
    """Pre-built widget URL (only when speaker_severity > 'none')."""

    recommended_reply: Optional[RecommendedReply] = None
    """Recommended reply content."""

    resource_query: Optional[str] = None
    """LLM-generated query for resource matching (e.g., 'LGBTQ youth bullying support')."""

    resource_tags: Optional[List[str]] = None
    """LLM-generated tags for specialized resources (e.g., ['cancer', 'terminal_illness'])."""

    reflection: Optional[str] = None
    """LLM reflection/reasoning (pre-scoring analysis)."""

    filter_result: Optional[FilterResult] = None
    """Filter stage results."""

    metadata: Optional[ResponseMetadata] = None
    """Metadata about the request/response."""


# =============================================================================
# Screen Types (for /v1/screen endpoint)
# =============================================================================


class ScreenRisk(BaseModel):
    """A single identified risk from screen classification."""

    model_config = {"extra": "allow"}

    type: RiskType
    """What type of harm."""

    subject: RiskSubject
    """Who is at risk."""

    severity: Severity
    """How severe."""

    imminence: Imminence
    """How soon."""

    confidence: float = Field(ge=0.0, le=1.0)
    """Confidence in this risk assessment (0.0-1.0)."""


class ScreenRecommendedReply(BaseModel):
    """Recommended supportive reply for screen response."""

    model_config = {"extra": "allow"}

    content: str
    """The recommended reply content."""

    source: Literal["llm_generated"]
    """Source of the reply (always 'llm_generated')."""


class ScreenCrisisResourcePrimary(BaseModel):
    """Primary crisis resource (e.g., 988 Lifeline)."""

    model_config = {"extra": "allow"}  # Allow extra fields from API

    name: str
    description: Optional[str] = None
    phone: Optional[str] = None
    text: Optional[str] = None  # API may return text_instructions instead
    text_instructions: Optional[str] = None
    chat_url: Optional[str] = None
    website_url: Optional[str] = None
    availability: Optional[str] = None
    languages: Optional[List[str]] = None


class ScreenCrisisResourceSecondary(BaseModel):
    """Secondary crisis resource (e.g., Crisis Text Line)."""

    model_config = {"extra": "allow"}  # Allow extra fields from API

    name: str
    description: Optional[str] = None
    text: Optional[str] = None  # API may return text_instructions instead
    text_instructions: Optional[str] = None
    sms_number: Optional[str] = None
    chat_url: Optional[str] = None
    website_url: Optional[str] = None
    availability: Optional[str] = None
    languages: Optional[List[str]] = None


class ScreenCrisisResources(BaseModel):
    """Crisis resources returned by /v1/screen endpoint."""

    primary: ScreenCrisisResourcePrimary
    secondary: List[ScreenCrisisResourceSecondary]


class ScreenDisplayText(BaseModel):
    """Suggested display text for crisis resources."""

    short: str
    """Short message (e.g., "If you're in crisis, call or text 988")."""

    detailed: str
    """Detailed message with more context."""


class ScreenDebugInfo(BaseModel):
    """Debug information for /v1/screen (only if requested)."""

    model: str
    latency_ms: int
    raw_response: Optional[str] = None


class ScreenResponse(BaseModel):
    """
    Response from /v1/screen endpoint.

    Multi-domain safety screening across all 9 risk types.
    Satisfies requirements for California SB243, NY Article 47.
    """

    model_config = {"extra": "allow"}  # Allow extra fields from API

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
    """Configuration for /v1/screen request."""

    country: Optional[str] = None
    """ISO country code for locale-specific resources (default: 'US')."""

    debug: Optional[bool] = None
    """Include debug info (latency, raw response)."""

    include_recommended_reply: Optional[bool] = None
    """Generate a recommended supportive reply (additional ~$0.0005 cost)."""


# =============================================================================
# Utility Constants
# =============================================================================

SEVERITY_SCORES = {
    "none": 0,
    "mild": 1,
    "moderate": 2,
    "high": 3,
    "critical": 4,
}

IMMINENCE_SCORES = {
    "not_applicable": 0,
    "chronic": 1,
    "subacute": 2,
    "urgent": 3,
    "emergency": 4,
}


# =============================================================================
# Utility Functions
# =============================================================================


def calculate_speaker_severity(risks: List[Risk]) -> Severity:
    """
    Calculate speaker severity from risks array.

    Only considers risks where subject='self' and subject_confidence > 0.5
    """
    speaker_risks = [r for r in risks if r.subject == "self" and r.subject_confidence > 0.5]

    if not speaker_risks:
        return "none"

    max_score = max(SEVERITY_SCORES[r.severity] for r in speaker_risks)

    for severity, score in SEVERITY_SCORES.items():
        if score == max_score:
            return severity  # type: ignore

    return "none"


def calculate_speaker_imminence(risks: List[Risk]) -> Imminence:
    """Calculate speaker imminence from risks array."""
    speaker_risks = [r for r in risks if r.subject == "self" and r.subject_confidence > 0.5]

    if not speaker_risks:
        return "not_applicable"

    max_score = max(IMMINENCE_SCORES[r.imminence] for r in speaker_risks)

    for imminence, score in IMMINENCE_SCORES.items():
        if score == max_score:
            return imminence  # type: ignore

    return "not_applicable"


def has_third_party_risk(risks: List[Risk]) -> bool:
    """Check if any third-party risk exists."""
    return any(r.subject == "other" and r.subject_confidence > 0.5 for r in risks)


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
