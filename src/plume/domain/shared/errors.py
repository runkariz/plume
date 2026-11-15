"""Domain errors. Every rule violation raised by the domain is a ``DomainError``."""


class DomainError(Exception):
    """Base class for domain rule violations."""


class InvalidIdentifierError(DomainError, ValueError):
    """An identifier (api id, build id, tag name, item id, hash) is malformed."""


class BuildSealedError(DomainError):
    """A sealed build is immutable; the requested change was refused."""


class EmptyBuildError(DomainError):
    """A build without items cannot be sealed."""


class UnknownItemError(DomainError, KeyError):
    """The item is not part of the build."""


class TagTargetError(DomainError):
    """A tag may only point at a sealed build of the same API."""
