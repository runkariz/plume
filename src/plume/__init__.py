"""Plume: API documentation knowledge base (immutable builds, tags, Postgres + pgvector, MCP)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("plume")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without install
    __version__ = "0.0.0"

__all__ = ["__version__"]
