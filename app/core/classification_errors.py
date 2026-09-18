"""Transport-independent errors with explicit HTTP mappings."""
from app.core.exceptions import AppException


class ClassificationError(AppException):
    def __init__(self, status: int, reason: str, message: str | None = None):
        code = {401: 30001, 403: 30002, 404: 50001, 409: 20002, 412: 20002,
                413: 20001, 415: 20001, 422: 20001, 428: 20001, 503: 90001}.get(status, 90001)
        super().__init__(message or reason, code, {"reason": reason})
        self.status_code = status
