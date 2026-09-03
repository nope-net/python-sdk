"""
NOPE Python SDK

Safety layer for chat & LLMs. Analyzes conversations for mental-health
and safeguarding risk.

Example:
    ```python
    from nope_net import NopeClient

    client = NopeClient(api_key="nope_live_...")
    result = client.evaluate(
        messages=[{"role": "user", "content": "I'm feeling down"}],
        config={"user_country": "US"}
    )

    print(f"Severity: {result.speaker_severity}")
    if result.resources and result.resources.get("primary"):
        print(f"  {result.resources['primary']['name']}: {result.resources['primary']['phone']}")
    ```
"""

from ._http import BalanceMeta, RateLimitMeta, ResponseMeta
from .client import AsyncNopeClient, NopeClient
from .errors import (
    NopeAuthError,
    NopeConnectionError,
    NopeError,
    NopeFeatureError,
    NopeInsufficientBalanceError,
    NopeNotFoundError,
    NopeRateLimitError,
    NopeServerError,
    NopeServiceUnavailableError,
    NopeValidationError,
)
from .types import (
    IMMINENCE_SCORES,
    SEVERITY_SCORES,
    AggregatedBehavior,
    CommunicationAssessment,
    CommunicationStyleAssessment,
    # Oversight types
    ConcernLevel,
    # Supporting types
    CrisisResource,
    DetectCountryResponse,
    DetectedBehavior,
    EvaluateConfig,
    EvaluateRequest,
    # Core response types
    EvaluateResponse,
    FilterResult,
    HumanIndicator,
    HumanIndicatorType,
    IPVFlags,
    LegalFlags,
    # Request types
    Message,
    OcularAxis,
    OcularMeta,
    # Ocular types
    OcularResponse,
    OcularSignals,
    OcularStability,
    OcularTrajectoryEntry,
    OpenStatus,
    OtherContact,
    OversightAnalysisResult,
    OversightAnalysisStrategy,
    OversightAnalyzeConfig,
    OversightAnalyzeResponse,
    OversightConversation,
    OversightConversationMetadata,
    OversightIngestConfig,
    OversightIngestConversationResult,
    OversightIngestError,
    OversightIngestResponse,
    OversightMessage,
    OversightSeverity,
    PreliminaryRisk,
    ProtectiveFactorsInfo,
    # Resources types
    RankedResource,
    RecommendedReply,
    ResourceByIdResponse,
    ResourcesConfig,
    ResourcesCountriesResponse,
    ResourcesResponse,
    ResourcesSmartResponse,
    ResponseMetadata,
    Risk,
    SafeguardingConcernFlags,
    # Screen types
    ScreenConfig,
    ScreenCrisisResourcePrimary,
    ScreenCrisisResources,
    ScreenCrisisResourceSecondary,
    ScreenDebugInfo,
    ScreenDisplayText,
    ScreenRecommendedReply,
    ScreenResponse,
    ScreenRisk,
    SignpostSearchResponse,
    # Signpost search types
    SignpostSearchResult,
    SignpostSearchTiming,
    StalkingFlags,
    Summary,
    ThirdPartyThreatFlags,
    Trajectory,
    TurnAnalysis,
    calculate_speaker_imminence,
    # Utility functions
    calculate_speaker_severity,
    has_third_party_risk,
)
from .webhook import (
    Webhook,
    WebhookConversation,
    WebhookDomainAssessment,
    WebhookFlags,
    WebhookPayload,
    WebhookResourceProvided,
    WebhookRiskSummary,
    WebhookSignatureError,
)

__version__ = "4.0.0"

__all__ = [
    # Clients
    "NopeClient",
    "AsyncNopeClient",
    # Errors
    "NopeError",
    "NopeAuthError",
    "NopeFeatureError",
    "NopeInsufficientBalanceError",
    "NopeNotFoundError",
    "NopeRateLimitError",
    "NopeValidationError",
    "NopeServerError",
    "NopeServiceUnavailableError",
    "NopeConnectionError",
    # Response meta side channel
    "ResponseMeta",
    "RateLimitMeta",
    "BalanceMeta",
    # Request types
    "Message",
    "EvaluateConfig",
    "EvaluateRequest",
    # Core response types
    "EvaluateResponse",
    "Risk",
    "Summary",
    "CommunicationAssessment",
    "CommunicationStyleAssessment",
    # Supporting types
    "CrisisResource",
    "OtherContact",
    "OpenStatus",
    "LegalFlags",
    "IPVFlags",
    "SafeguardingConcernFlags",
    "ThirdPartyThreatFlags",
    "StalkingFlags",
    "ProtectiveFactorsInfo",
    "FilterResult",
    "PreliminaryRisk",
    "RecommendedReply",
    "ResponseMetadata",
    # Screen types
    "ScreenConfig",
    "ScreenResponse",
    "ScreenRisk",
    "ScreenRecommendedReply",
    "ScreenCrisisResources",
    "ScreenCrisisResourcePrimary",
    "ScreenCrisisResourceSecondary",
    "ScreenDisplayText",
    "ScreenDebugInfo",
    # Resources types
    "RankedResource",
    "ResourcesConfig",
    "ResourcesResponse",
    "ResourcesSmartResponse",
    "ResourceByIdResponse",
    "ResourcesCountriesResponse",
    "DetectCountryResponse",
    # Signpost search types
    "SignpostSearchResult",
    "SignpostSearchTiming",
    "SignpostSearchResponse",
    # Ocular types
    "OcularResponse",
    "OcularAxis",
    "OcularSignals",
    "OcularStability",
    "OcularTrajectoryEntry",
    "OcularMeta",
    # Oversight types
    "ConcernLevel",
    "Trajectory",
    "OversightSeverity",
    "HumanIndicatorType",
    "OversightAnalysisStrategy",
    "OversightMessage",
    "OversightConversationMetadata",
    "OversightConversation",
    "DetectedBehavior",
    "AggregatedBehavior",
    "TurnAnalysis",
    "HumanIndicator",
    "OversightAnalysisResult",
    "OversightAnalyzeConfig",
    "OversightAnalyzeResponse",
    "OversightIngestConfig",
    "OversightIngestConversationResult",
    "OversightIngestError",
    "OversightIngestResponse",
    # Utility functions
    "calculate_speaker_severity",
    "calculate_speaker_imminence",
    "has_third_party_risk",
    "SEVERITY_SCORES",
    "IMMINENCE_SCORES",
    # Webhook verification
    "Webhook",
    "WebhookSignatureError",
    "WebhookPayload",
    "WebhookRiskSummary",
    "WebhookDomainAssessment",
    "WebhookFlags",
    "WebhookResourceProvided",
    "WebhookConversation",
]
