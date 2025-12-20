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
    "emergency_number", "crisis_line", "text_line", "chat_service", "support_service"
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
    "support_directory_or_tool",
    "emergency_services",
]


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

    dry_run: Optional[bool] = None
    """Dry run mode (evaluate but don't log/trigger webhooks). Default: false."""

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


class CrisisResource(BaseModel):
    """A crisis resource (helpline, text line, etc.)."""

    type: CrisisResourceType
    name: str
    name_local: Optional[str] = None
    """Native script name (e.g., いのちの電話) for non-English resources."""
    phone: Optional[str] = None
    text_instructions: Optional[str] = None
    chat_url: Optional[str] = None
    whatsapp_url: Optional[str] = None
    """WhatsApp deep link (e.g., 'https://wa.me/18002738255')."""
    website_url: Optional[str] = None
    availability: Optional[str] = None
    is_24_7: Optional[bool] = None
    languages: Optional[List[str]] = None
    description: Optional[str] = None
    resource_kind: Optional[CrisisResourceKind] = None
    service_scope: Optional[List[str]] = None
    population_served: Optional[List[str]] = None
    priority_tier: Optional[CrisisResourcePriorityTier] = None
    source: Optional[Literal["database", "web_search"]] = None


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

    access_level: Optional[Literal["unauthenticated", "authenticated", "admin"]] = None
    is_admin: Optional[bool] = None
    messages_truncated: Optional[bool] = None
    input_format: Optional[Literal["structured", "text_blob"]] = None
    api_version: Literal["v1"] = "v1"


class EvaluateResponse(BaseModel):
    """Response from /v1/evaluate endpoint."""

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

    filter_result: Optional[FilterResult] = None
    """Filter stage results."""

    metadata: Optional[ResponseMetadata] = None
    """Metadata about the request/response."""


# =============================================================================
# Screen Types (for /v1/screen endpoint)
# =============================================================================


class ScreenCrisisResourcePrimary(BaseModel):
    """Primary crisis resource (e.g., 988 Lifeline)."""

    name: str
    description: str
    phone: str
    text: str
    chat_url: str
    website_url: str
    availability: str
    languages: List[str]


class ScreenCrisisResourceSecondary(BaseModel):
    """Secondary crisis resource (e.g., Crisis Text Line)."""

    name: str
    description: str
    text: str
    sms_number: str
    chat_url: str
    website_url: str
    availability: str
    languages: List[str]


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

    Lightweight crisis screening for SB243 compliance.
    Uses C-SSRS framework for evidence-based severity assessment.
    """

    referral_required: bool
    """Should crisis resources be shown?"""

    crisis_type: Optional[Literal["suicidal_ideation", "self_harm"]]
    """Type of crisis detected (null if none)."""

    cssrs_level: int
    """C-SSRS level (0-5) - evidence-based severity measure."""

    self_harm_detected: bool
    """Self-harm (NSSI) specifically detected."""

    confidence: float
    """Confidence in assessment (0-1)."""

    rationale: str
    """Brief rationale for assessment."""

    resources: Optional[ScreenCrisisResources] = None
    """Crisis resources to display (only when referral_required)."""

    widget_url: Optional[str] = None
    """Pre-built widget URL (only when referral_required)."""

    display_text: Optional[ScreenDisplayText] = None
    """Suggested display text (only when referral_required)."""

    request_id: str
    """Request ID for audit trail."""

    timestamp: str
    """ISO timestamp for audit trail."""

    debug: Optional[ScreenDebugInfo] = None
    """Debug info (only if requested)."""


class ScreenConfig(BaseModel):
    """Configuration for /v1/screen request."""

    debug: Optional[bool] = None
    """Include debug info (latency, raw response)."""


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
