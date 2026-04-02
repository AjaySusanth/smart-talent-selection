"""Custom exception classes for the Smart Talent Selection Engine.

Each exception maps to a specific error domain and can be caught by
the global FastAPI exception handler (Phase 6) for RFC 7807 responses.
"""


class ParsingError(Exception):
    """Raised when document text extraction fails (Azure DI or fallback)."""

    def __init__(self, message: str, source: str = "unknown"):
        self.source = source
        super().__init__(message)


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""

    pass


class RankingError(Exception):
    """Raised when the ranking pipeline encounters an unrecoverable error."""

    pass


class StorageError(Exception):
    """Raised when object storage operations fail."""

    pass
