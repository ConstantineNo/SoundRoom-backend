"""Unified business exception types."""

from typing import Any, Optional


class AppException(Exception):
    """Base application exception with error code."""
    def __init__(self, message: str, code: int = 1, detail: Any = None):
        self.message = message
        self.code = code
        self.detail = detail
        super().__init__(message)


class NotFoundError(AppException):
    """Resource not found (maps to HTTP 404)."""
    def __init__(self, message: str = "Resource not found", code: int = 50001):
        super().__init__(message, code)


class AuthenticationError(AppException):
    """Authentication failure (maps to HTTP 401)."""
    def __init__(self, message: str = "Authentication required", code: int = 30001):
        super().__init__(message, code)


class PermissionDeniedError(AppException):
    """Permission denied (maps to HTTP 403)."""
    def __init__(self, message: str = "Permission denied", code: int = 30002):
        super().__init__(message, code)


class ValidationError(AppException):
    """Input validation failure (maps to HTTP 400)."""
    def __init__(self, message: str, code: int = 20001):
        super().__init__(message, code)


class ConflictError(AppException):
    """Resource conflict, e.g. duplicate (maps to HTTP 409)."""
    def __init__(self, message: str, code: int = 20002):
        super().__init__(message, code)


# ── Error code registry ──

ERROR_CODES = {
    # Success
    0: "ok",

    # Generic
    1: "internal_error",

    # Validation 2xxxx
    20001: "validation_error",
    20002: "duplicate_entry",

    # Auth 3xxxx
    30001: "authentication_required",
    30002: "permission_denied",

    # Not found 5xxxx
    50001: "not_found",

    # System 9xxxx
    90001: "internal_server_error",
}
