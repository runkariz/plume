"""Redaction of reported questions and notes before they are stored (the raw text never is).

Rules, in order, each replacing the match with a fixed marker:
1. URLs keep scheme, host and path; a query string or fragment becomes "?[query]".
2. Credentials after Bearer / Basic / Token -> [token]; JWTs and known key prefixes -> [secret].
3. The value of a secret-looking key -> [secret], the key stays: after "=" always; after ":" or
   a space only when the value looks secret (6+ characters with a digit or symbol), so prose
   such as "access token: how do I ..." stays.
4. Emails -> [email]; IBAN-like account numbers -> [account]; IPv4 / IPv6 -> [ip].
5. Any 24+ character run of key characters mixing letters and digits -> [secret].
5a. A company name: capitalised words before a legal form (GmbH, AG, Ltd, LLC, Inc, SAS, BV,
   SRL, ...) -> [company].
5b. An identifier after a cue word (customer / company / shop / seller / merchant / tenant /
   warehouse / location / store / account / order / vendor / supplier / client / user, with an
   optional number / no / nr / id / code / name) -> [id] when it holds a digit or is a code
   (letters joined by "-" or "_" with a capital: WH-Hamburg-Nord); prose words stay. A
   standalone code of a few capitals, a dash and 4+ digits (KD-004711) -> [id], except
   standards (ISO-8601, RFC-3339, SHA-256, UTF-8, ...).
6. Phone / card-like digit groups (9+ digits with spaces or dashes) and plain runs of 9+ digits
   -> [number]; runs of 7-8 digits too, unless ``keep_error_codes`` and the run follows
   "error", "code" or "errorCode" (an API's error code, not a person's number).
Text is capped at MAX_TEXT characters after redaction.

check_call paths become templates: all-digit, UUID, long hex or redacted segments -> {}; the
query string's names join the parameter names and its values are dropped. Parameter entries
keep their names only, unless ``keep_rpc_method`` keeps the value of ``method`` (an RPC
operation name such as aliexpress.solution.order.get).
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlsplit

MAX_TEXT = 500
MAX_NAME = 64


@dataclass(frozen=True, slots=True)
class RedactionPolicy:
    """The two switchable rules (both off: the strict default)."""

    keep_error_codes: bool = False  # keep 7-8 digit runs after "error" / "code" / "errorCode"
    keep_rpc_method: bool = False  # keep the value of the RPC selector `method` in check_call


_URL = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s\"'<>]+", re.IGNORECASE)
_AUTH = re.compile(r"\b(bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{6,}", re.IGNORECASE)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}(?:\.[A-Za-z0-9_-]*)?")
_PREFIXED = re.compile(
    r"\b(?:sk|pk|rk)[-_](?:live|test)?[-_]?[A-Za-z0-9]{8,}|\bghp_[A-Za-z0-9]{8,}"
    r"|\bxox[abpr]-[A-Za-z0-9-]{8,}|\bAKIA[A-Z0-9]{12,}|\bAIza[A-Za-z0-9_-]{20,}"
)
_SECRET_KEY_NAMES = (  # a pattern of key names, no secret
    r"(?:api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|client[_-]?secret|secret|"  # noqa: S105
    r"password|passwd|pwd|token|auth(?:orization)?|signature|sig|session(?:[_-]?id)?|cookie|key)"
)
_KEY_VALUE = re.compile(rf"\b({_SECRET_KEY_NAMES})(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&]+)", re.I)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){10,30}\b")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"\b(?:[0-9a-f]{1,4}:){3,7}[0-9a-f]{1,4}\b", re.IGNORECASE)
_LONG_KEYLIKE = re.compile(r"(?<![A-Za-z0-9_+/=.-])[A-Za-z0-9_+/=.-]{24,}(?![A-Za-z0-9_+/=.-])")
_GROUPED_DIGITS = re.compile(r"\+?\d[\d\s-]{7,}\d")
_DIGITS = re.compile(r"\d{7,}")
_CODE_BEFORE = re.compile(r"(?:error|code|errorcode)[\s:#=_-]*$", re.IGNORECASE)
_LEGAL_FORMS = (
    r"GmbH|AG|KG|OHG|UG|KGaA|SE|e\.K\.|Ltd\.?|Limited|LLC|LLP|PLC|Inc\.?|Corp\.?|Co\.|SAS|"
    r"SARL|S\.A\.|SA|S\.p\.A\.|SpA|S\.r\.l\.|SRL|B\.V\.|BV|N\.V\.|NV|Oy|AB|ApS|A/S|AS|"
    r"Sp\. z o\.o\.|s\.r\.o\.|Pty"
)
# 1-4 capitalised words (or "&"), then the legal form; "& Co. KG" chains
_COMPANY = re.compile(
    rf"\b(?:[A-Z][\w'.-]*\s+(?:&\s+)?){{1,4}}(?:(?:{_LEGAL_FORMS})\s+)?(?:{_LEGAL_FORMS})(?![\w])"
)
_CUES = (
    r"customer|company|shop|seller|merchant|tenant|warehouse|location|store|account|order|"
    r"vendor|supplier|client|user|kunde|lager"
)
_CUE_ID = re.compile(
    rf"\b((?:{_CUES})(?:\s+(?:number|no\.?|nr\.?|id|code|name|#))?\s*[:#=]?\s*)"
    r"([A-Za-z0-9][A-Za-z0-9_./-]*)",
    re.IGNORECASE,
)
_STANDARDS = frozenset({"ISO", "RFC", "EN", "DIN", "SHA", "UTF", "HTTP", "TLS", "IEC", "ECMA",
                        "ISBN", "EAN", "GTIN", "UPC", "CVE", "PCI"})  # fmt: skip
_CODE = re.compile(r"\b([A-Z]{1,4})-\d{4,}\b")
_MARKERS = (
    "[token]", "[secret]", "[email]", "[account]", "[ip]", "[number]", "?[query]", "[company]",
    "[id]",
)  # fmt: skip


def _cue_id(m: re.Match[str]) -> str:
    """The identifier after a cue word, when it is one: a digit, or a code ("-"/"_" joining
    letters with a capital); prose ("for warehouse stock levels") stays."""
    value = m.group(2).rstrip(".")
    rest = m.group(2)[len(value) :]
    coded = bool(re.search(r"[-_]", value)) and any(c.isupper() for c in value)
    if any(c.isdigit() for c in value) or coded:
        return f"{m.group(1)}[id]{rest}"
    return m.group(0)


def _mixed(s: str) -> bool:
    return any(c.isdigit() for c in s) and any(c.isalpha() for c in s)


STRICT = RedactionPolicy()


def redact_text(text: str | None, policy: RedactionPolicy = STRICT) -> tuple[str, int]:
    """The text with every rule applied, and how many markers it now holds."""
    if not text:
        return "", 0

    def url(m: re.Match[str]) -> str:
        parts = urlsplit(m.group(0))
        rest = "?[query]" if parts.query or parts.fragment else ""
        return f"{parts.scheme}://{parts.netloc}{template_path(parts.path)[0]}{rest}"

    s = _URL.sub(url, text)
    s = _AUTH.sub(lambda m: f"{m.group(1)} [token]", s)
    s = _JWT.sub("[secret]", s)
    s = _PREFIXED.sub("[secret]", s)
    s = _KEY_VALUE.sub(_key_value, s)
    s = _EMAIL.sub("[email]", s)
    s = _IBAN.sub("[account]", s)
    s = _IPV6.sub("[ip]", s)
    s = _IPV4.sub("[ip]", s)
    s = _COMPANY.sub("[company]", s)
    s = _CUE_ID.sub(_cue_id, s)
    s = _CODE.sub(lambda m: m.group(0) if m.group(1) in _STANDARDS else "[id]", s)
    s = _LONG_KEYLIKE.sub(lambda m: "[secret]" if _mixed(m.group(0)) else m.group(0), s)
    s = _GROUPED_DIGITS.sub(_grouped, s)
    current = s

    def digits(m: re.Match[str]) -> str:
        run = m.group(0)
        if len(run) <= 8 and policy.keep_error_codes and _CODE_BEFORE.search(current[: m.start()]):
            return run
        return "[number]"

    s = _DIGITS.sub(digits, s)
    count = sum(s.count(mark) for mark in _MARKERS) - sum(text.count(mark) for mark in _MARKERS)
    return s[:MAX_TEXT], max(count, 0)


def _key_value(m: re.Match[str]) -> str:
    """key=value (code-like) always; key: value only when the value looks like a secret (has
    a digit or symbol), so prose like "access token: how do I ..." stays."""
    value = m.group(3).strip("\"'")
    secretish = len(value) >= 6 and bool(re.search(r"[\d_./+=-]", value))
    if "=" in m.group(2) or secretish:
        return f"{m.group(1)}{m.group(2)}[secret]"
    return m.group(0)


def _grouped(m: re.Match[str]) -> str:
    run = m.group(0)
    if sum(c.isdigit() for c in run) < 9 or not re.search(r"[\s-]", run):
        return run  # a plain run: the digit rule decides
    return "[number]"


_SEGMENT_ID = re.compile(
    r"^(?:\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{16,})$",
    re.IGNORECASE,
)


def template_path(path: str) -> tuple[str, int]:
    """A path with its identifying segments as {} (placeholders the caller wrote stay)."""
    count = 0
    segments = []
    for seg in path.split("/"):
        if not seg or (seg.startswith("{") and seg.endswith("}")):
            segments.append(seg)
            continue
        red, n = redact_text(seg)
        if _SEGMENT_ID.match(seg) or n or (len(seg) >= 24 and _mixed(seg)):
            segments.append("{}")
            count += 1
        else:
            segments.append(red)
    return "/".join(segments), count


_NAME = re.compile(r"^[A-Za-z0-9_.\[\]$@-]{1,64}$")


def call_template(
    path: str, entries: list[str], policy: RedactionPolicy = STRICT
) -> tuple[str, list[str], int]:
    """A check_call path as a template, and the parameter names: the given entries ("name" or
    "name=value") and the path's query string, values dropped (``keep_rpc_method`` keeps the
    value of ``method``). A full URL keeps scheme and host."""
    given = path.strip()
    parts = urlsplit(given)
    template, count = template_path(parts.path or "/")
    if parts.scheme and parts.netloc:
        template = f"{parts.scheme}://{parts.netloc}{template}"
    raw = [*entries, *(f"{k}={v}" for k, v in parse_qsl(parts.query, keep_blank_values=True))]
    names: list[str] = []
    for entry in raw:
        name, eq, value = entry.partition("=")
        name = name.strip()
        if not _NAME.match(name):
            count += 1
            continue
        keep = policy.keep_rpc_method and name.lower() == "method" and eq and value.strip()
        item = f"{name}={redact_text(value.strip())[0]}" if keep else name
        if item not in names:
            names.append(item)
    return template, names, count


def redact_name(name: str | None) -> tuple[str | None, int]:
    """A short name (a fact name, a client name): redacted and capped at MAX_NAME."""
    if not name:
        return None, 0
    red, n = redact_text(name)
    return red[:MAX_NAME], n
