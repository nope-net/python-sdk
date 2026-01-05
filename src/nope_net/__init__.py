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

    print(f"Severity: {result.summary.speaker_severity}")
    for resource in result.crisis_resources:
        print(f"  {resource.name}: {resource.phone}")
    ```
"""

from .client import AsyncNopeClient, NopeClient
from .errors import (
    NopeAuthError,
    NopeConnectionError,
    NopeError,
    NopeFeatureError,
    NopeRateLimitError,
    NopeServerError,
    NopeValidationError,
)
from .types import (
    # Request types
    Message,
    EvaluateConfig,
    EvaluateRequest,
    # Core response types
    EvaluateResponse,
    Risk,
    Summary,
    CommunicationAssessment,
    CommunicationStyleAssessment,
    # Supporting types
    CrisisResource,
    LegalFlags,
    IPVFlags,
    SafeguardingConcernFlags,
    ThirdPartyThreatFlags,
    ProtectiveFactorsInfo,
    FilterResult,
    PreliminaryRisk,
    RecommendedReply,
    ResponseMetadata,
    # Screen types
    ScreenConfig,
    ScreenResponse,
    ScreenCrisisResources,
    ScreenCrisisResourcePrimary,
    ScreenCrisisResourceSecondary,
    ScreenDisplayText,
    ScreenDebugInfo,
    # Oversight types
    ConcernLevel,
    Trajectory,
    OversightSeverity,
    HumanIndicatorType,
    OversightAnalysisStrategy,
    OversightMessage,
    OversightConversationMetadata,
    OversightConversation,
    DetectedBehavior,
    AggregatedBehavior,
    TurnAnalysis,
    HumanIndicator,
    OversightAnalysisResult,
    OversightAnalyzeConfig,
    OversightAnalyzeResponse,
    OversightIngestConfig,
    OversightIngestConversationResult,
    OversightIngestError,
    OversightIngestResponse,
    # Utility functions
    calculate_speaker_severity,
    calculate_speaker_imminence,
    has_third_party_risk,
    SEVERITY_SCORES,
    IMMINENCE_SCORES,
)
from .webhook import (
    Webhook,
    WebhookSignatureError,
    WebhookPayload,
    WebhookRiskSummary,
    WebhookDomainAssessment,
    WebhookFlags,
    WebhookResourceProvided,
    WebhookConversation,
)

__version__ = "1.2.0"

__all__ = [
    # Clients
    "NopeClient",
    "AsyncNopeClient",
    # Errors
    "NopeError",
    "NopeAuthError",
    "NopeFeatureError",
    "NopeRateLimitError",
    "NopeValidationError",
    "NopeServerError",
    "NopeConnectionError",
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
    "LegalFlags",
    "IPVFlags",
    "SafeguardingConcernFlags",
    "ThirdPartyThreatFlags",
    "ProtectiveFactorsInfo",
    "FilterResult",
    "PreliminaryRisk",
    "RecommendedReply",
    "ResponseMetadata",
    # Screen types
    "ScreenConfig",
    "ScreenResponse",
    "ScreenCrisisResources",
    "ScreenCrisisResourcePrimary",
    "ScreenCrisisResourceSecondary",
    "ScreenDisplayText",
    "ScreenDebugInfo",
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
