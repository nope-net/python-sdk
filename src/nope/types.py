"""
NOPE SDK Types

Pydantic models for API requests and responses.
"""

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


# =============================================================================
# Enums / Literals
# =============================================================================

Severity = Literal["none", "mild", "moderate", "high", "critical"]
Imminence = Literal["not_applicable", "chronic", "subacute", "urgent", "emergency"]
RiskDomain = Literal["self", "others", "dependent_at_risk", "victimisation"]
SelfSubtype = Literal["suicidal_or_self_injury", "self_neglect", "other"]
DependentSubtype = Literal["child", "adult_at_risk", "animal_or_other"]
VictimisationSubtype = Literal[
    "IPV_intimate_partner",
    "family_non_intimate",
    "trafficking_exploitation",
    "community_violence",
    "institutional_abuse",
    "other",
]
EvidenceGrade = Literal["strong", "moderate", "weak", "consensus", "none"]
CrisisResourceType = Literal[
    "emergency_number", "crisis_line", "text_line", "chat_service", "support_service"
]
CrisisResourceKind = Literal["helpline", "reporting_portal", "directory", "self_help_site"]
CrisisResourcePriorityTier = Literal[
    "primary_national_crisis",
    "secondary_national_crisis",
    "specialist_issue_crisis",
    "population_specific_crisis",
    "support_info_and_advocacy",
    "support_directory_or_tool",
    "emergency_services",
]

# Proposed response evaluation types
ResponseIssueSeverity = Literal["critical", "serious", "concerning"]
ResponseIssue = Literal[
    # Critical
    "method_or_means_detail",
    "suicide_self_harm_encouragement",
    "crisis_signal_ignored",
    "crisis_resources_missing",
    "victim_blaming",
    "harmful_advice",
    # Serious
    "dismissive_of_distress",
    "disbelief_of_disclosure",
    "inappropriate_probing",
    "reinforces_harmful_beliefs",
    # Concerning
    "scripted_robotic_tone",
    "overwhelming_or_unfocused",
]
ResponseRecommendation = Literal["use", "augment", "replace"]


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
    """Policy ID to use. Default: 'default_mh'."""

    dry_run: Optional[bool] = None
    """Dry run mode (evaluate but don't log/trigger webhooks). Default: false."""

    return_assistant_reply: Optional[bool] = None
    """Whether to return a safe assistant reply. Default: true."""

    assistant_safety_mode: Optional[Literal["template", "generate"]] = None
    """How NOPE should generate the recommended reply."""

    use_multiple_judges: Optional[bool] = None
    """Use multiple judges for higher confidence. Default: false."""

    models: Optional[List[str]] = None
    """Specify exact models to use (bypasses adaptive selection)."""

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

    proposed_response: Optional[str] = None
    """Optional proposed AI response to evaluate for appropriateness."""


# =============================================================================
# Response Types
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


class PresentationModifiers(BaseModel):
    """Cross-cutting clinical features (HOW risk manifests)."""

    psychotic_features: Optional[bool] = None
    substance_involved: Optional[bool] = None
    cognitive_impairment: Optional[bool] = None
    personality_features: Optional[bool] = None
    acute_decompensation: Optional[bool] = None
    self_neglect_severe: Optional[bool] = None


class SafeguardingFlags(BaseModel):
    """Legal/reporting markers."""

    child_at_risk: Optional[bool] = None
    adult_at_risk: Optional[bool] = None
    duty_to_warn_others: Optional[bool] = None
    mandatory_reporting_possible: Optional[bool] = None


class ProtectiveFactorsInfo(BaseModel):
    """Evidence-based strengths that reduce risk."""

    protective_factors: Optional[List[str]] = None
    protective_factor_strength: Optional[Literal["weak", "moderate", "strong"]] = None


class ThirdPartyThreat(BaseModel):
    """Third party threat indicator."""

    present: bool
    identifiable_victim: bool
    confidence: float
    rationale: str
    evidence_grade: Optional[EvidenceGrade] = None


class IntimatePartnerViolence(BaseModel):
    """IPV risk indicator."""

    risk_level: Literal["standard", "elevated", "severe", "extreme"]
    confidence: float
    strangulation_history: Optional[bool] = None
    escalation_pattern: Optional[bool] = None
    evidence_grade: Optional[EvidenceGrade] = None


class ChildSafeguarding(BaseModel):
    """Child safeguarding urgency."""

    urgency: Literal["routine", "prompt", "urgent", "emergency"]
    confidence: float
    basic_needs_unmet: Optional[bool] = None
    immediate_danger: Optional[bool] = None
    evidence_grade: Optional[EvidenceGrade] = None


class VulnerableAdultSafeguarding(BaseModel):
    """Vulnerable adult safeguarding."""

    urgency: Literal["routine", "prompt", "urgent", "emergency"]
    confidence: float
    evidence_grade: Optional[EvidenceGrade] = None


class AnimalCrueltyIndicator(BaseModel):
    """Animal cruelty indicator."""

    present: bool
    confidence: float
    evidence_grade: Optional[EvidenceGrade] = None


class LegalFlags(BaseModel):
    """Legal/clinical flags with evidence grades."""

    third_party_threat: Optional[ThirdPartyThreat] = None
    intimate_partner_violence: Optional[IntimatePartnerViolence] = None
    child_safeguarding: Optional[ChildSafeguarding] = None
    vulnerable_adult_safeguarding: Optional[VulnerableAdultSafeguarding] = None
    animal_cruelty_indicator: Optional[AnimalCrueltyIndicator] = None


class GlobalAssessment(BaseModel):
    """Global summary of the assessment."""

    overall_severity: Severity
    overall_imminence: Imminence
    primary_concerns: List[str]
    language: Optional[str] = None
    locale: Optional[str] = None


class BaseDomainAssessment(BaseModel):
    """Base fields for domain assessments."""

    severity: Severity
    imminence: Imminence
    confidence: float = Field(ge=0.0, le=1.0)
    risk_features: List[str]
    risk_types: Optional[List[str]] = None
    reasoning: Optional[str] = None


class SelfDomainAssessment(BaseDomainAssessment):
    """Self domain assessment."""

    domain: Literal["self"]
    self_subtype: SelfSubtype


class OthersDomainAssessment(BaseDomainAssessment):
    """Others domain assessment."""

    domain: Literal["others"]


class DependentAtRiskAssessment(BaseDomainAssessment):
    """Dependent at risk assessment."""

    domain: Literal["dependent_at_risk"]
    dependent_subtype: DependentSubtype


class VictimisationAssessment(BaseDomainAssessment):
    """Victimisation assessment."""

    domain: Literal["victimisation"]
    victimisation_subtype: Optional[VictimisationSubtype] = None


DomainAssessment = Union[
    SelfDomainAssessment,
    OthersDomainAssessment,
    DependentAtRiskAssessment,
    VictimisationAssessment,
]


class RecommendedReply(BaseModel):
    """Recommended reply content."""

    content: str
    source: Literal["template", "llm_generated", "llm_validated_candidate"]
    notes: Optional[str] = None


class ProposedResponseEvaluation(BaseModel):
    """Evaluation of a proposed AI response."""

    appropriate: bool
    """Whether the proposed response is appropriate for the conversation context."""

    issues: List[ResponseIssue]
    """Issues detected in the proposed response (empty if appropriate)."""

    recommendation: ResponseRecommendation
    """Recommendation for what to do: 'use', 'augment', or 'replace'."""

    reasoning: Optional[str] = None
    """Brief explanation of why the response is/isn't appropriate."""


class CopingRecommendation(BaseModel):
    """A coping/support recommendation."""

    category: Literal[
        "self_soothing",
        "social_support",
        "professional_support",
        "safety_planning",
        "means_safety",
    ]
    evidence_grade: EvidenceGrade


class ResponseMetadata(BaseModel):
    """Metadata about the request/response."""

    access_level: Optional[Literal["unauthenticated", "authenticated", "admin"]] = None
    is_admin: Optional[bool] = None
    messages_truncated: Optional[bool] = None
    messages_original_count: Optional[int] = None
    messages_kept_count: Optional[int] = None
    features_available: Optional[List[str]] = None
    input_format: Optional[Literal["structured", "text_blob"]] = None
    api_version: Literal["v1"] = "v1"


class EvaluateResponse(BaseModel):
    """Response from /v1/evaluate endpoint."""

    domains: List[DomainAssessment]
    """Domain-specific assessments."""

    global_: GlobalAssessment = Field(alias="global")
    """Global summary. Note: accessed as .global_ due to Python reserved word."""

    legal_flags: Optional[LegalFlags] = None
    """Legal/clinical flags with evidence grades."""

    presentation_modifiers: Optional[PresentationModifiers] = None
    """Cross-cutting presentation modifiers."""

    safeguarding_flags: Optional[SafeguardingFlags] = None
    """Safeguarding flags."""

    protective_factors_info: Optional[ProtectiveFactorsInfo] = None
    """Protective factors."""

    confidence: float = Field(ge=0.0, le=1.0)
    """Overall confidence in assessment."""

    agreement: Optional[float] = None
    """Judge agreement (if multiple judges)."""

    crisis_resources: List[CrisisResource]
    """Crisis resources for user's region."""

    widget_url: Optional[str] = None
    """Pre-built widget URL for embedding crisis resources (only present when severity is not 'none')."""

    recommended_reply: Optional[RecommendedReply] = None
    """Recommended reply content."""

    proposed_response_evaluation: Optional[ProposedResponseEvaluation] = None
    """Evaluation of the proposed_response (if provided in request)."""

    coping_recommendations: Optional[List[CopingRecommendation]] = None
    """High-level coping/support categories."""

    metadata: Optional[ResponseMetadata] = None
    """Metadata about the request/response."""

    model_config = {"populate_by_name": True}
