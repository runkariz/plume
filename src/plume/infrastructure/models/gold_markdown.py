"""The eval tester's markdown report -> a ``plume.model-gold.v1`` file.

Reads the title ``# <Concept> across <apis>, tested ...`` and the table under
``## Expected mapping (gold)``::

    | canonical field | shopify | woocommerce | conversion |
    | total | `total_price` | `total` | money-decimal-string: string amount |
    | lines[].sku | `line_items[].sku` | not available | |

A cell is a path, several paths joined by ``+``, ``not available`` (or ``n/a``), or ``—`` / empty
(not judged: left out). The conversion cell is ``<kind>: <note>`` for every API, or per API
``<api>: <kind> <note>; ...``; text that names no known kind is kept as an ``other`` note.
A nested field (``lines[].sku``, ``address.city``) becomes a sub-field of its parent.
"""

import re
from typing import Any

from plume.domain.models.canonical_model import CONVERSION_KINDS
from plume.domain.models.model_gold import SCHEMA, parse_gold

_TITLE = re.compile(r"^#\s+(.+?)\s+across\s+(.+?)(?:,\s*tested.*)?$", re.I | re.M)
_SECTION = re.compile(r"^##\s+Expected mapping", re.I | re.M)
_NOT_JUDGED = {"", "-", "\u2014", "\u2013", "?"}  # empty, dashes: not judged
_NOT_AVAILABLE = {"not available", "n/a", "na", "none", "not-available"}


class GoldImportError(ValueError):
    pass


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _clean(text: str) -> str:
    return text.replace("`", "").strip()


def _conversion(text: str) -> dict[str, Any] | None:
    text = _clean(text)
    if not text:
        return None
    kind, _, note = text.partition(":")
    kind = kind.strip().lower()
    if kind in CONVERSION_KINDS:
        return {"kind": kind, **({"note": note.strip()} if note.strip() else {})}
    first = text.split()[0].lower().rstrip(",;")
    if first in CONVERSION_KINDS:
        rest = text[len(first) :].strip(" :,-")
        return {"kind": first, **({"note": rest} if rest else {})}
    return {"kind": "other", "note": text}


def _conversions(text: str, apis: list[str]) -> dict[str, dict[str, Any]]:
    """Per API: ``api: kind note; api: ...``, or one conversion for every API."""
    parts = [p.strip() for p in _clean(text).split(";") if p.strip()]
    per_api = {}
    for part in parts:
        head, sep, rest = part.partition(":")
        if sep and head.strip().lower() in {a.lower() for a in apis}:
            api = next(a for a in apis if a.lower() == head.strip().lower())
            conv = _conversion(rest)
            if conv:
                per_api[api] = conv
    if per_api:
        return per_api
    conv = _conversion(text)
    return dict.fromkeys(apis, conv) if conv else {}


def _cell(text: str) -> dict[str, Any] | None:
    value = _clean(text)
    if value.lower() in _NOT_JUDGED:
        return None
    if value.lower() in _NOT_AVAILABLE:
        return {"notAvailable": True}
    paths = [p.strip() for p in re.split(r"\s+\+\s+|,\s*", value) if p.strip()]
    return {"paths": paths}


_OPS = re.compile(r"^##\s+Operations", re.I | re.M)
_ENDPOINT = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+(/[^\s`(),;]+)")
_KINDS = (("adjust", "adjust"), ("set", "set"), ("read", "read"), ("get", "read"),
          ("list", "read"), ("create", "create"), ("add", "create"), ("update", "update"),
          ("delete", "delete"), ("remove", "delete"))  # fmt: skip


def _operations(text: str, apis: list[str]) -> list[dict[str, Any]]:
    """The "## Operations" table: per operation and API its endpoints, or "not available"."""
    start = _OPS.search(text)
    if start is None:
        return []
    lines = []
    for ln in text[start.end() :].splitlines()[1:]:
        if ln.startswith("## "):
            break
        if ln.strip().startswith("|"):
            lines.append(ln)
    if len(lines) < 2:
        return []
    header = [_clean(h).lower() for h in _cells(lines[0])]
    cols = {api: header.index(api.lower()) for api in apis if api.lower() in header}
    out = []
    for line in lines[1:]:
        row = _cells(line)
        if set("".join(row)) <= set("-: ") or not _clean(row[0]):
            continue
        name = _clean(row[0])
        words = re.findall(r"[a-z]+", name.lower())
        kind = next((k for w, k in _KINDS if w in words), "other")
        cells: dict[str, Any] = {}
        for api, col in cols.items():
            cell = _clean(row[col]) if col < len(row) else ""
            found = [f"{m.group(1)} {m.group(2)}" for m in _ENDPOINT.finditer(cell)]
            if found:
                cells[api] = {"endpoints": list(dict.fromkeys(found))}
            elif cell.lower() in _NOT_AVAILABLE:
                cells[api] = {"notAvailable": True}
        out.append({"name": name, "kind": kind, "apis": cells})
    return out


def _insert(fields: list[dict[str, Any]], path: list[str], field: dict[str, Any]) -> None:
    head, *rest = path
    node = next((f for f in fields if f["name"] == head), None)
    if not rest:
        if node is None:
            fields.append({"name": head, **field})
        else:
            node.update({k: v for k, v in field.items() if k != "fields"})
        return
    if node is None:
        node = {"name": head, "apis": {}}
        fields.append(node)
    _insert(node.setdefault("fields", []), rest, field)


def import_markdown(text: str, group: str | None = None, held_out: bool = False) -> dict[str, Any]:
    title = _TITLE.search(text)
    if title is None:
        raise GoldImportError("no '# <Concept> across <apis>' title")
    concept = re.sub(r"\s*\(.*?\)\s*", " ", title.group(1)).strip()  # "Order (+ order line)"
    start = _SECTION.search(text)
    if start is None:
        raise GoldImportError("no '## Expected mapping (gold)' section")
    lines = [ln for ln in text[start.end() :].splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        raise GoldImportError("the expected mapping table is empty")
    header = _cells(lines[0])
    conv_col = next((i for i, h in enumerate(header) if h.lower().startswith("conversion")), None)
    api_cols = [i for i in range(1, len(header)) if i != conv_col]
    apis = [_clean(header[i]) for i in api_cols]
    fields: list[dict[str, Any]] = []
    for line in lines[1:]:
        row = _cells(line)
        if set("".join(row)) <= set("-: "):
            continue  # the |---|---| separator
        name = _clean(row[0])
        if not name:
            continue
        convs = (
            _conversions(row[conv_col], apis)
            if conv_col is not None and conv_col < len(row)
            else {}
        )
        cells = {}
        for api, col in zip(apis, api_cols, strict=True):
            cell = _cell(row[col]) if col < len(row) else None
            if cell is None:
                continue
            if "paths" in cell and api in convs:
                cell["conversion"] = convs[api]
            cells[api] = cell
        path = [p for p in name.replace("[]", "").split(".") if p]
        _insert(fields, path, {"apis": cells})
    gold: dict[str, Any] = {
        "schema": SCHEMA,
        "concept": concept,
        "apis": apis,
        "heldOut": held_out,
        "fields": fields,
    }
    operations = _operations(text, apis)
    if operations:
        gold["operations"] = operations
    if group is not None:
        gold["group"] = group
    parse_gold(gold, "import")  # the result must be a valid gold file
    return gold
