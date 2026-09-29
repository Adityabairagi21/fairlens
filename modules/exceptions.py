"""Custom exceptions used across the application.

Having our own exception types lets the UI show a precise, friendly message
for each failure instead of catching a generic ``Exception``.
"""


class ScreeningAppError(Exception):
    """Base class for every error raised by this application."""


class ValidationError(ScreeningAppError):
    """Raised when user-supplied data fails validation.

    ``field`` names the offending input so the UI can point at it.
    """

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


class DuplicateCandidateError(ScreeningAppError):
    """Raised when a candidate ID (or email) already exists."""


class DuplicateJobError(ScreeningAppError):
    """Raised when a job role ID or title already exists."""


class RecordNotFoundError(ScreeningAppError):
    """Raised when a candidate or job ID does not exist."""


class DataFileError(ScreeningAppError):
    """Raised when a data file is missing, unreadable or corrupted."""
