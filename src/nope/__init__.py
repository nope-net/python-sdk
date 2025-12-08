"""
NOPE Python SDK

Safety layer for chat & LLMs. Analyzes conversations for mental-health
and safeguarding risk.

Example:
    ```python
    from nope import NopeClient

    client = NopeClient(api_key="nope_live_...")
    result = client.evaluate(
        messages=[{"role": "user", "content": "I'm feeling down"}],
        config={"user_country": "US"}
    )

    print(f"Severity: {result.global_.overall_severity}")
    for resource in result.crisis_resources:
        print(f"  {resource.name}: {resource.phone}")
    ```
"""

from .client import AsyncNopeClient, NopeClient
from .errors import (
    NopeAuthError,
    NopeConnectionError,
    NopeError,
    NopeRateLimitError,
    NopeServerError,
    NopeValidationError,
)
from .types import (
    CopingRecommendation,
    CrisisResource,
    DependentAtRiskAssessment,
    DomainAssessment,
    EvaluateConfig,
    EvaluateResponse,
    GlobalAssessment,
    LegalFlags,
    Message,
    OthersDomainAssessment,
    PresentationModifiers,
    ProposedResponseEvaluation,
    ProtectiveFactorsInfo,
    RecommendedReply,
    SafeguardingFlags,
    SelfDomainAssessment,
    VictimisationAssessment,
)

__version__ = "0.1.0"

__all__ = [
    # Clients
    "NopeClient",
    "AsyncNopeClient",
    # Errors
    "NopeError",
    "NopeAuthError",
    "NopeRateLimitError",
    "NopeValidationError",
    "NopeServerError",
    "NopeConnectionError",
    # Request types
    "Message",
    "EvaluateConfig",
    # Response types
    "EvaluateResponse",
    "GlobalAssessment",
    "DomainAssessment",
    "SelfDomainAssessment",
    "OthersDomainAssessment",
    "DependentAtRiskAssessment",
    "VictimisationAssessment",
    "CrisisResource",
    "LegalFlags",
    "PresentationModifiers",
    "SafeguardingFlags",
    "ProtectiveFactorsInfo",
    "RecommendedReply",
    "ProposedResponseEvaluation",
    "CopingRecommendation",
]
