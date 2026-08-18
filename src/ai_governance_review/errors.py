"""Expected errors raised for invalid user-controlled input."""


class ValidationError(Exception):
    """An actionable validation failure that is safe to show to a user."""

    def __init__(self, message: str, details: list[str] | None = None) -> None:
        super().__init__(message)
        self.details = details or []

    def __str__(self) -> str:
        message = super().__str__()
        return f"{message}: {'; '.join(self.details)}" if self.details else message
