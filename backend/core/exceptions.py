"""Domain exceptions. The API layer maps them to HTTP status codes."""
from __future__ import annotations


class DomainError(Exception):
    """Base class. ``code`` is a stable machine-readable identifier."""

    status_code = 400
    code = "domain_error"

    def __init__(self, message: str, *, code: str | None = None, details: object | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details


class ValidationFailed(DomainError):
    status_code = 422
    code = "validation_failed"


class NotFound(DomainError):
    status_code = 404
    code = "not_found"


class PermissionDenied(DomainError):
    status_code = 403
    code = "permission_denied"


class Conflict(DomainError):
    status_code = 409
    code = "conflict"


class PeriodClosed(DomainError):
    status_code = 409
    code = "period_closed"


class WorkflowError(DomainError):
    status_code = 409
    code = "workflow_error"


class AuthenticationFailed(DomainError):
    status_code = 401
    code = "authentication_failed"
