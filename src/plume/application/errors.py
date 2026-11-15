"""Application errors (above the domain rules)."""


class ApplicationError(Exception):
    code = "error"


class NotFoundError(ApplicationError, LookupError):
    code = "not_found"


class IncompleteBuildError(ApplicationError):
    """A pipeline step was asked to run before the steps it depends on finished."""

    code = "incomplete_build"


class SourcePackageError(ApplicationError, ValueError):
    """The input package is unreadable or breaks the package contract."""

    code = "invalid_package"


class EmbeddingError(ApplicationError):
    code = "embedding_failed"


class GateFailedError(ApplicationError):
    """The build failed its quality gate; it cannot be published without force."""

    code = "gate_failed"
