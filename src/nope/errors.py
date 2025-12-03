"""
NOPE SDK Exceptions

Structured error handling for API interactions.
"""

from typing import Optional


class NopeError(Exception):
    """Base exception for all NOPE SDK errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_body = response_body

    def __str__(self) -> str:
        if self.status_code:
            return f"[{self.status_code}] {self.message}"
        return self.message


class NopeAuthError(NopeError):
    """
    Authentication error (HTTP 401).

    Raised when the API key is invalid, expired, or missing.
    """

    def __init__(
        self,
        message: str = "Invalid or missing API key",
        response_body: Optional[str] = None,
    ):
        super().__init__(message, status_code=401, response_body=response_body)


class NopeRateLimitError(NopeError):
    """
    Rate limit exceeded (HTTP 429).

    Check retry_after for when to retry.
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[float] = None,
        response_body: Optional[str] = None,
    ):
        super().__init__(message, status_code=429, response_body=response_body)
        self.retry_after = retry_after  # seconds

    def __str__(self) -> str:
        base = super().__str__()
        if self.retry_after:
            return f"{base} (retry after {self.retry_after}s)"
        return base


class NopeValidationError(NopeError):
    """
    Validation error (HTTP 400).

    Raised when the request payload is invalid.
    """

    def __init__(
        self,
        message: str = "Invalid request",
        response_body: Optional[str] = None,
    ):
        super().__init__(message, status_code=400, response_body=response_body)


class NopeServerError(NopeError):
    """
    Server error (HTTP 5xx).

    Raised when the NOPE API encounters an internal error.
    """

    def __init__(
        self,
        message: str = "Server error",
        status_code: int = 500,
        response_body: Optional[str] = None,
    ):
        super().__init__(message, status_code=status_code, response_body=response_body)


class NopeConnectionError(NopeError):
    """
    Connection error.

    Raised when unable to connect to the NOPE API.
    """

    def __init__(
        self,
        message: str = "Failed to connect to NOPE API",
        original_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.original_error = original_error
