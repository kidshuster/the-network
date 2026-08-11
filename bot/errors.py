from __future__ import annotations


class UserFacingError(Exception):
    """An expected failure whose message is safe to show to Discord users."""

    def __init__(
        self,
        message: str,
        *,
        title: str = "Operation Failed",
        code: str = "operation_failed",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.title = title
        self.code = code
