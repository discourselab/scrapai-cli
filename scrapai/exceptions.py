"""ScrapAI exception classes."""

from typing import Any


class ScrapAIError(Exception):
    """Base exception for all ScrapAI errors."""

    pass


class SpiderNotFoundError(ScrapAIError):
    """Raised when a spider is not found in the database."""

    def __init__(self, name: str, project: str | None = None):
        self.name = name
        self.project = project
        msg = f"Spider '{name}' not found"
        if project:
            msg += f" in project '{project}'"
        super().__init__(msg)


class ProjectNotFoundError(ScrapAIError):
    """Raised when a project is not found."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Project '{name}' not found")


class GenerationFailedError(ScrapAIError):
    """Raised when spider generation fails after all retries."""

    def __init__(self, url: str, error: str | None = None):
        self.url = url
        self.error = error
        msg = f"Failed to generate spider for '{url}'"
        if error:
            msg += f": {error}"
        super().__init__(msg)


class LLMNotConfiguredError(ScrapAIError):
    """Raised when LLM configuration is missing."""

    def __init__(self, message: str | None = None):
        msg = (
            message
            or "LLM not configured. Set SCRAPAI_LLM_API, SCRAPAI_LLM_KEY, and SCRAPAI_LLM_MODEL env vars."
        )
        super().__init__(msg)


class CrawlError(ScrapAIError):
    """Raised when a crawl fails."""

    def __init__(self, spider: str, error: str | None = None):
        self.spider = spider
        self.error = error
        msg = f"Crawl failed for spider '{spider}'"
        if error:
            msg += f": {error}"
        super().__init__(msg)


class ExportError(ScrapAIError):
    """Raised when export fails."""

    def __init__(self, message: str):
        super().__init__(message)


class QueryNotAllowedError(ScrapAIError):
    """Raised when db_query attempts a non-SELECT statement."""

    def __init__(self):
        super().__init__(
            "Only SELECT queries are allowed. Use db_query() for read-only queries."
        )


class ValidationError(ScrapAIError):
    """Raised when spider config validation fails."""

    def __init__(self, message: str):
        super().__init__(message)


class ScrapAIConfigError(ScrapAIError):
    """Raised when required configuration is missing or invalid."""

    def __init__(self, message: str):
        super().__init__(message)
