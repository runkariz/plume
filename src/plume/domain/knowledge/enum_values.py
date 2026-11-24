"""A scalar enum schema's own values (a model whose root is ``{type: string, enum: [...]}``)."""

from collections.abc import Mapping
from typing import Any


def enum_values(schema: Mapping[str, Any]) -> list[tuple[str, str | None]]:
    """The schema's enum values with their x-enum-descriptions (a dict keyed by value, or a list
    in the enum's order); [] for an object schema (it has properties) or no enum."""
    enum = schema.get("enum")
    if not isinstance(enum, list) or not enum or isinstance(schema.get("properties"), dict):
        return []
    described = schema.get("x-enum-descriptions")
    out: list[tuple[str, str | None]] = []
    for i, value in enumerate(enum):
        if isinstance(described, dict):
            text = described.get(str(value))
        elif isinstance(described, list) and i < len(described):
            text = described[i]
        else:
            text = None
        out.append((str(value), text.strip() if isinstance(text, str) and text.strip() else None))
    return out
