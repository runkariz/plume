"""The producer's manifest.json ``warnings`` (``"<code>: <text>"``) and the user-facing notices
Plume shows for the codes it knows, on the section they concern. Unknown codes stay
maintainer-only."""

from dataclasses import dataclass

AUTH = "auth"
ENVIRONMENTS = "environments"
SECTIONS = (AUTH, ENVIRONMENTS)


@dataclass(frozen=True, slots=True)
class PackageWarning:
    code: str
    text: str


@dataclass(frozen=True, slots=True)
class Notice:
    code: str
    section: str
    text: str


SIGNED = "Every request must be signed (see the setup text); there is no ready auth option yet."
KNOWN: dict[str, tuple[str, str]] = {
    "default-environment-by-order": (
        ENVIRONMENTS,
        "The docs name no default; this one is first in the spec. Choose your region.",
    ),
    "auth-requires-signature": (AUTH, SIGNED),
    "auth-none-public-sources": (AUTH, SIGNED),
    "auth-needs-core-change": (
        AUTH,
        "This API's auth uses a variant the connector can't express yet; calls won't "
        "authenticate until Kariz supports it (see the setup text).",
    ),
}


def parse(raw: object) -> list[PackageWarning]:
    """manifest.json ``warnings`` as {code, text}: the code is the text before the first ":"
    (the whole entry, trimmed, when there is none). Non-strings and blanks are skipped."""
    if not isinstance(raw, list):
        return []
    out = []
    for entry in raw:
        if not isinstance(entry, str) or not entry.strip():
            continue
        code, sep, _ = entry.partition(":")
        out.append(PackageWarning(code=code.strip() if sep else entry.strip(), text=entry.strip()))
    return out


def notices(warnings: list[PackageWarning], section: str | None = None) -> list[Notice]:
    """User-facing notices for the known codes, one per distinct text and section (in order),
    only the given section's when one is named."""
    out: list[Notice] = []
    seen: set[tuple[str, str]] = set()
    for w in warnings:
        known = KNOWN.get(w.code)
        if known is None or (section is not None and known[0] != section):
            continue
        if (known[0], known[1]) in seen:
            continue
        seen.add((known[0], known[1]))
        out.append(Notice(code=w.code, section=known[0], text=known[1]))
    return out
