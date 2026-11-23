"""``knowledge-export/`` v1 (``index.json`` schema ``plume.knowledge-export.v1``).

Layout: ``index.json`` (pages, each may carry x-kariz-conflicts; ``complete``),
``pages/*.md`` (YAML front matter: ``source`` URL and ``items`` [{id, kind, method, path, name,
anchor}], then the cleaned page text), ``rules.json`` (rules {id, scope: <endpoint id> |
"resource", type, text, quote, anchor, sourceUrl, confidence, resource, endpointIds,
x-kariz-conflicts}), optionally ``gold-questions.json`` and ``unit-links.json``
(``plume.unit-links.v1``: links [{unitId, endpointIds, linkBasis}], the
page/slug links of knowledge units; read even without ``index.json``).

The reader enriches each endpoint document with the page section its anchor points at and
with the rules scoped to it, and turns each page's remaining text (intro, property tables) plus
its resource-level rules into one guide document.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from plume.domain.knowledge.document import CONFLICTS_KEY

SCHEMA_V1 = "plume.knowledge-export.v1"
# a unit-links basis: the unit's sample merely calls the endpoint (it is not about it)
SAMPLE_CALL = "sample-call"
ZWSP = "\u200b"
MAX_SECTION_CHARS = 6000
# A page guide is a navigation aid (intro, property overview, resource rules), not a second copy
# of every endpoint on the page: pages whose endpoint sections could not be located would
# otherwise hold the whole page and outrank the endpoints themselves.
MAX_INTRO_CHARS = 6000
_COMMENT = re.compile(r"<!--.*?-->", re.S)


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    scope: str
    type: str
    text: str
    quote: str
    source_url: str | None
    anchor: str | None
    confidence: float | None
    resource: str | None
    endpoint_ids: tuple[str, ...] = ()
    # A rule stated on several pages (stream merges repeats): the other pages' URLs.
    source_urls: tuple[str, ...] = ()
    # x-kariz-conflicts on the rule (raw items): shown on every document the rule is shown on
    conflicts: tuple[Any, ...] = ()

    @property
    def urls(self) -> tuple[str, ...]:
        """Every page the rule is stated on: sourceUrl first, then sourceUrls (no repeats)."""
        first = (self.source_url,) if self.source_url else ()
        return tuple(dict.fromkeys(u for u in (*first, *self.source_urls) if u))

    def line(self) -> str:
        conf = f", confidence {self.confidence:.2f}" if self.confidence is not None else ""
        return f'- {self.text} ({self.type}{conf}; source: "{self.quote}")'


@dataclass
class ExportPage:
    file: str
    source_url: str
    title: str
    intro: str
    sections: dict[str, tuple[str, str]] = field(default_factory=dict)  # item id -> (anchor, text)
    items: list[tuple[str, str]] = field(default_factory=list)  # (item id, "METHOD name")
    conflicts: list[Any] = field(default_factory=list)  # the index entry's x-kariz-conflicts
    # endpoint items the page only calls in a sample (every unit link to them is sample-call)
    sample_calls: list[str] = field(default_factory=list)

    @property
    def split(self) -> bool:
        """True when the page could be cut into its endpoints' sections (or lists none)."""
        return not self.items or len(self.sections) * 2 >= len(self.items)


@dataclass
class KnowledgeExport:
    complete: bool
    pages: list[ExportPage]
    rules: list[Rule]
    gold_path: Path | None


def detect(root: Path) -> bool:
    index = root / "index.json"
    if not index.is_file():
        return False
    try:
        return bool(json.loads(index.read_text(encoding="utf-8")).get("schema") == SCHEMA_V1)
    except json.JSONDecodeError:
        return False


def _front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    meta = yaml.safe_load(text[3:end]) or {}
    return (meta if isinstance(meta, dict) else {}), text[end + 4 :]


def _heading_pattern(anchor: str) -> re.Pattern[str]:
    words = [w for w in anchor.lstrip("#").split("-") if w]
    body = r"[\s\-]+".join(re.escape(w) for w in words)
    return re.compile(body + r"\s*" + ZWSP, re.I)


_SYMBOLS = frozenset('{}[]()<>;="$\\/')
TOKEN_DENSITY = 0.08
MIN_PROSE_GAP = 4


def strip_code(text: str) -> str:
    """Drop code-like runs (examples, JSON payloads) from scraped prose.

    A token is code when its own share of code symbols ({}[]()<>;="$\\/) is high; prose runs
    shorter than four tokens between code runs count as code too. Runs of code become a single
    " … ". Generic: no knowledge of a site's markup."""
    tokens = text.split()
    code = [sum(ch in _SYMBOLS for ch in t) / len(t) > TOKEN_DENSITY for t in tokens]
    i = 0
    while i < len(tokens):  # absorb short prose gaps between code
        if code[i]:
            i += 1
            continue
        j = i
        while j < len(tokens) and not code[j]:
            j += 1
        if i > 0 and j < len(tokens) and j - i < MIN_PROSE_GAP:
            for k in range(i, j):
                code[k] = True
        i = j
    out: list[str] = []
    for token, is_code in zip(tokens, code, strict=True):
        if not is_code:
            out.append(token)
        elif not out or out[-1] != "…":
            out.append("…")
    return " ".join(out)


def _cap(text: str, limit: int = MAX_INTRO_CHARS) -> str:
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def _title_from_url(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return " ".join(w.capitalize() for w in re.split(r"[-_]", slug) if w) or url


def parse_page(path: Path) -> ExportPage:
    meta, body = _front_matter(path.read_text(encoding="utf-8-sig"))
    body = _COMMENT.sub("", body).strip()
    source = str(meta.get("source") or "")
    starts: list[tuple[int, int, str, str]] = []  # (start, heading end, item id, anchor)
    for item in meta.get("items") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        if not str(item.get("anchor") or "").lstrip("#").strip():
            continue  # no anchor, or an empty fragment
        m = _heading_pattern(str(item["anchor"])).search(body)
        if m is not None:
            starts.append((m.start(), m.end(), str(item["id"]), str(item["anchor"])))
    starts.sort()
    page = ExportPage(
        file=path.name,
        source_url=source,
        title=_title_from_url(source),
        intro=_cap(
            strip_code((body[: starts[0][0]] if starts else body).replace(ZWSP, "").strip())
        ),
    )
    page.items = [
        (str(i["id"]), f"{i.get('method', '')} {i.get('name', '')}".strip())
        for i in meta.get("items") or []
        if isinstance(i, dict) and i.get("id")
    ]
    for i, (start, _, item_id, anchor) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(body)
        text = strip_code(body[start:end].replace(ZWSP, "").strip())
        if len(text) > MAX_SECTION_CHARS:
            text = text[:MAX_SECTION_CHARS].rstrip() + " …"
        page.sections.setdefault(item_id, (anchor, text))
    return page


def load(root: Path) -> KnowledgeExport:
    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    pages = []
    for p in index.get("pages", []):
        if isinstance(p, dict) and (root / str(p.get("file", ""))).is_file():
            page = parse_page(root / p["file"])
            page.conflicts = _conflicts(p)
            pages.append(page)
    rules: list[Rule] = []
    rules_file = root / "rules.json"
    if rules_file.is_file():
        data = json.loads(rules_file.read_text(encoding="utf-8"))
        for r in data.get("rules", []) if isinstance(data, dict) else []:
            if not isinstance(r, dict) or not r.get("text") or not r.get("quote"):
                continue
            conf = r.get("confidence")
            rules.append(
                Rule(
                    rule_id=str(r.get("id", "")),
                    scope=str(r.get("scope", "resource")),
                    type=str(r.get("type", "rule")),
                    text=str(r["text"]),
                    quote=str(r["quote"]),
                    source_url=r.get("sourceUrl"),
                    anchor=r.get("anchor")
                    if str(r.get("anchor") or "").lstrip("#").strip()
                    else None,
                    confidence=float(conf) if isinstance(conf, int | float) else None,
                    resource=r.get("resource"),
                    endpoint_ids=_id_list(r.get("endpointIds")),
                    source_urls=_id_list(r.get("sourceUrls")),
                    conflicts=tuple(_conflicts(r)),
                )
            )
    gold = root / "gold-questions.json"
    return KnowledgeExport(
        complete=bool(index.get("complete", False)),
        pages=pages,
        rules=rules,
        gold_path=gold if gold.is_file() else None,
    )


def _conflicts(entry: dict[str, Any]) -> list[Any]:
    """An entry's x-kariz-conflicts items (raw; the reader skips malformed ones)."""
    items = entry.get(CONFLICTS_KEY)
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def _id_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict.fromkeys(v.strip() for v in value if isinstance(v, str) and v.strip()))


UNIT_LINKS = "unit-links.json"


def load_unit_links(root: Path) -> dict[str, tuple[tuple[str, ...], str]]:
    """``unit-links.json``: knowledge unit id -> (producer endpoint ids, linkBasis). Entries
    without endpoints are left out (hub pages link nothing). Missing file: empty."""
    path = root / UNIT_LINKS
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, tuple[tuple[str, ...], str]] = {}
    for entry in data.get("links", []) if isinstance(data, dict) else []:
        if not isinstance(entry, dict) or not isinstance(entry.get("unitId"), str):
            continue
        ids = _id_list(entry.get("endpointIds"))
        if ids:
            basis = entry.get("linkBasis")
            out[entry["unitId"]] = (ids, basis if isinstance(basis, str) and basis else "export")
    return out


def without_sample_calls(
    export: KnowledgeExport, links: dict[str, tuple[tuple[str, ...], str]]
) -> KnowledgeExport:
    """A page's endpoint item that its knowledge units link to ONLY by sample-call is not what
    the page documents (Meta's reminder-ads page lists POST /act_{id}/campaigns because its
    sample creates a campaign): it leaves the page's items and sections, so the page's rules
    and its "documentation page" role do not reach that endpoint."""
    for page in export.pages:
        units = [i.removeprefix("knowledge:") for i, _ in page.items if i.startswith("knowledge:")]
        dropped = []
        for item_id, _ in page.items:
            if item_id.startswith("knowledge:"):
                continue
            bases = [links[u][1] for u in units if u in links and item_id in links[u][0]]
            if bases and all(b == SAMPLE_CALL for b in bases):
                dropped.append(item_id)
        if dropped:
            page.items = [(i, label) for i, label in page.items if i not in dropped]
            page.sections = {i: v for i, v in page.sections.items() if i not in dropped}
            page.sample_calls = dropped
    return export
