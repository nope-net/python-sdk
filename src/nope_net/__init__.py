"""
NOPE Python SDK

Safety layer for chat and LLMs: risk classification for conversations, AI
behaviour oversight, crisis resources, and the billing and webhook management
routes of the NOPE API.

Example:
    ```python
    from nope_net import NopeClient

    client = NopeClient(api_key="nope_live_...")
    result = client.evaluate(
        messages=[{"role": "user", "content": "I'm feeling down"}],
        config={"country": "US"},
    )

    print(f"Severity: {result.speaker_severity}")
    if result.resources:
        print(f"  {result.resources.primary.name}: {result.resources.primary.phone}")
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
    ConcernLevel,
    CrisisResource,
    CrisisResourceKind,
    CrisisResourcePriorityTier,
    CrisisResourceType,
    DetectCountryResponse,
    DetectedBehavior,
    EvaluateConfig,
    EvaluateMetadata,
    EvaluateRequest,
    EvaluateResource,
    EvaluateResources,
    EvaluateResponse,
    HoursConfidence,
    HumanIndicator,
    HumanIndicatorType,
    Imminence,
    Message,
    OcularAxis,
    OcularMeta,
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
    RankedResource,
    ResourceByIdResponse,
    ResourceProminence,
    ResourcesConfig,
    ResourcesCountriesResponse,
    ResourcesResponse,
    ResourcesSmartResponse,
    Risk,
    RiskSubject,
    RiskType,
    ScreenConfig,
    ScreenCrisisResources,
    ScreenDebugInfo,
    ScreenRecommendedReply,
    ScreenResponse,
    ScreenRisk,
    ScreenRiskSubject,
    Severity,
    SignpostSearchResponse,
    SignpostSearchResult,
    SignpostSearchTiming,
    Trajectory,
    TruncationWarning,
    TurnAnalysis,
    calculate_speaker_imminence,
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
    "__version__",
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
    # Enums / literals
    "RiskSubject",
    "ScreenRiskSubject",
    "RiskType",
    "Severity",
    "Imminence",
    "CrisisResourceType",
    "CrisisResourceKind",
    "CrisisResourcePriorityTier",
    "HoursConfidence",
    "ResourceProminence",
    # Evaluate
    "Message",
    "EvaluateConfig",
    "EvaluateRequest",
    "EvaluateResponse",
    "EvaluateMetadata",
    "EvaluateResource",
    "EvaluateResources",
    "Risk",
    # Crisis resources
    "CrisisResource",
    "OtherContact",
    "OpenStatus",
    # Screen (deprecated)
    "ScreenConfig",
    "ScreenResponse",
    "ScreenRisk",
    "ScreenRecommendedReply",
    "ScreenCrisisResources",
    "ScreenDebugInfo",
    # Resources / signpost
    "RankedResource",
    "ResourcesConfig",
    "ResourcesResponse",
    "ResourcesSmartResponse",
    "ResourceByIdResponse",
    "ResourcesCountriesResponse",
    "DetectCountryResponse",
    "SignpostSearchResult",
    "SignpostSearchTiming",
    "SignpostSearchResponse",
    # Ocular
    "OcularResponse",
    "OcularAxis",
    "OcularSignals",
    "OcularStability",
    "OcularTrajectoryEntry",
    "OcularMeta",
    # Oversight
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
    "TruncationWarning",
    # Utilities
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
