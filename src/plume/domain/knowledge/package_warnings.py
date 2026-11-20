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
    doc_ids: tuple[str, ...] = ()  # the guides that explain it (auth / signing)


SIGNED = "Every request must be signed (see the setup text); there is no ready auth option yet."
SIGNED_WITH_AUTH = (
    "Every request must also be signed (see the setup text); Kariz can't sign requests yet, "
    "so calls will fail even with this auth."
)
UNSIGNED = (
    "The docs name no auth scheme for this API, and there is no ready auth option yet "
    "(see the setup text)."
)
SETUP_TEXT = "(see the setup text)"
NONE_PUBLIC = "auth-none-public-sources"  # signing, or no scheme at all: the evidence decides
# Signing codes: when the package has an auth scheme of its own, any of them says the signing
# comes on top of it (the rule is whether a scheme exists, not which code is present).
SIGNING_CODES = ("auth-requires-signature", "auth-none-public-sources", "auth-signed-request")
WITH_AUTH: dict[str, str] = dict.fromkeys(SIGNING_CODES, SIGNED_WITH_AUTH)
KNOWN: dict[str, tuple[str, str]] = {
    "default-environment-by-order": (
        ENVIRONMENTS,
        "The docs name no default; this one is first in the spec. Choose your region.",
    ),
    "sandbox-host-not-in-sources": (
        ENVIRONMENTS,
        "The docs mention a sandbox, but no source gives its address, so only production is "
        "listed.",
    ),
    "auth-requires-signature": (AUTH, SIGNED),
    "auth-none-public-sources": (AUTH, SIGNED),
    "auth-signed-request": (AUTH, SIGNED),
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


def notices(
    warnings: list[PackageWarning],
    section: str | None = None,
    has_auth: bool = False,
    *,
    signed: bool | None = None,
    guides: tuple[tuple[str, str], ...] = (),
) -> list[Notice]:
    """User-facing notices for the known codes, one per distinct text and section (in order),
    only the given section's when one is named. ``has_auth``: the package has an auth scheme
    (some codes then say the signing comes on top of it). ``signed``: whether the build shows
    signing (False: ``auth-none-public-sources`` says no scheme is documented; None: assume
    signing). ``guides`` ((doc id, title), ...): the API's auth / signing guides, named in
    auth notices instead of "the setup text" and listed as their doc ids."""
    out: list[Notice] = []
    seen: set[tuple[str, str]] = set()
    for w in warnings:
        known = KNOWN.get(w.code)
        if known is None or (section is not None and known[0] != section):
            continue
        where, text = known[0], (WITH_AUTH.get(w.code) if has_auth else None) or known[1]
        if w.code == NONE_PUBLIC and signed is False and not has_auth:
            text = UNSIGNED
        doc_ids: tuple[str, ...] = ()
        if where == AUTH and guides and SETUP_TEXT in text:
            text = text.replace(SETUP_TEXT, f"(see: {'; '.join(t for _, t in guides)})")
            doc_ids = tuple(d for d, _ in guides)
        if (where, text) in seen:
            continue
        seen.add((where, text))
        out.append(Notice(code=w.code, section=where, text=text, doc_ids=doc_ids))
    return out
