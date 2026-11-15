"""Deterministic concept suggestions across 2..N APIs (no LLM).

A concept is a normalised resource or model name (``Order``, ``DraftOrder`` -> ``order``,
``draftorder``). Per API it is ``direct`` (an endpoint resource or a model has that name),
``derived`` (only fields mention it, e.g. ``order_id``) or ``absent``.
"""

import re
from collections import defaultdict
from dataclasses import dataclass

from plume.application.errors import ApplicationError
from plume.application.ports.fact_index import FactIndex
from plume.application.ports.search_index import DocumentSummary, SearchIndex
from plume.application.reader.resolve import BuildResolver, ResolvedBuild
from plume.domain.knowledge.document import DocumentKind
from plume.domain.knowledge.fact import FactKind

# Generic and timestamp words: a model or resource with one of these names (e.g. Mirakl's
# "Updated", "Attributes", "Data / Entities") is a part of something else, never a concept.
_NOISE = frozenset(
    {
        "general", "default", "misc", "other", "error", "errors", "api", "app", "data", "datum",
        "updated", "created", "deleted", "modified", "date", "time", "timestamp", "from", "to",
        "latest", "attribute", "entity", "value", "page", "pagination", "link", "input",
        "output", "context", "detail", "summary", "reference", "range", "selection", "info",
        "information", "meta", "metadata", "result", "response", "request", "list", "property",
        "field", "parameter", "param", "option", "setting", "label", "period", "count", "total",
        "status", "type", "key", "id", "name", "object", "body", "payload", "record", "item",
        "filter", "query", "search", "batch", "bulk", "boolean", "string", "integer", "number",
        "float", "double", "decimal", "array", "null", "any", "map", "admin", "v1", "v2", "v3",
        "create", "update", "delete", "remove", "add",
    }
)  # fmt: skip
NOISE = _NOISE
_WRITE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_OPERATION = {
    "GET": "read",
    "POST": "create",
    "PUT": "update",
    "PATCH": "update",
    "DELETE": "delete",
}
MAX_APIS = 6
DEFAULT_LIMIT = 24
MAX_LIMIT = 100


class ModelInputError(ApplicationError, ValueError):
    code = "invalid_input"


def _singular(word: str) -> str:
    """English plural -> singular for resource names (``taxes`` -> ``tax``, ``addresses`` ->
    ``address``, ``categories`` -> ``category``, ``orders`` -> ``order``)."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("sses", "xes", "ches", "shes", "zes")) and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")) and len(word) > 3:
        return word[:-1]
    return word


def concept_key(name: str) -> str:
    return _singular(re.sub(r"[^a-z0-9]", "", name.lower()))


def concept_label(name: str) -> str:
    """``line_items`` / ``LineItems`` -> ``Line Item`` (the last word made singular)."""
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).replace("_", " ").replace("-", " ").split()
    if not words:
        return name
    words[-1] = _singular(words[-1].lower())
    return " ".join(w.capitalize() for w in words)


@dataclass(frozen=True, slots=True)
class ApiConceptCounts:
    """What one API documents about a concept (all 0 when it is derived or absent)."""

    models: int
    endpoints: int
    operations: tuple[str, ...]  # read | create | update | delete
    fields: int


@dataclass(frozen=True, slots=True)
class ConceptSuggestion:
    key: str
    name: str
    reason: str
    likely_fields: int
    coverage: dict[str, str]  # api -> direct | derived | absent
    operations: tuple[str, ...]
    difficulty: tuple[str, str]  # (tone, label)
    doc_ids: dict[str, tuple[str, ...]]  # api -> documents of this concept
    api_counts: dict[str, ApiConceptCounts]

    @property
    def present(self) -> int:
        return sum(v != "absent" for v in self.coverage.values())

    @property
    def in_all(self) -> bool:
        return all(v != "absent" for v in self.coverage.values())

    @property
    def writes(self) -> bool:
        return "write" in self.operations


@dataclass(frozen=True, slots=True)
class SuggestFilter:
    q: str | None = None
    only: str = "multi"  # multi | single | all
    require: tuple[str, ...] = ()
    in_all: bool = False
    write_only: bool = False
    limit: int = DEFAULT_LIMIT
    offset: int = 0


@dataclass(frozen=True, slots=True)
class SuggestCounts:
    all: int  # multi-API concepts matching q + require
    in_all: int
    write: int
    single: int


@dataclass(frozen=True, slots=True)
class Suggestions:
    apis: tuple[ResolvedBuild, ...]
    concepts: tuple[ConceptSuggestion, ...]  # this page
    total: int  # matching every filter
    limit: int
    offset: int
    counts: SuggestCounts
    not_modeled: int  # single-API concepts (matching q + require)
    not_modeled_examples: tuple[str, ...]

    @property
    def next_offset(self) -> int | None:
        nxt = self.offset + len(self.concepts)
        return nxt if nxt < self.total else None


def resolve_apis(resolver: BuildResolver, apis: list[str]) -> tuple[ResolvedBuild, ...]:
    unique = list(dict.fromkeys(a.strip() for a in apis if a.strip()))
    if not 2 <= len(unique) <= MAX_APIS:
        raise ModelInputError(f"pick 2..{MAX_APIS} different APIs")
    return tuple(resolver.resolve(a) for a in unique)


def _last_literal(path: str) -> str:
    """``/api/{version}/orders/{id}.json`` -> ``orders``; id-list and count literals are skipped
    (``/product_listings/product_ids.json`` -> ``product_listings``)."""
    for seg in reversed(path.strip("/").split("/")):
        name = seg.split(".", 1)[0]
        if name and "{" not in name and not name.endswith(("_id", "_ids")) and name != "count":
            return name
    return ""


def concept_docs(
    summaries: list[DocumentSummary],
) -> dict[str, list[DocumentSummary]]:
    """Group an API's endpoints and models by concept key."""
    out: dict[str, list[DocumentSummary]] = defaultdict(list)
    for s in summaries:
        if s.kind is DocumentKind.ENDPOINT:
            key = concept_key(s.resource or "")
            if (not key or key in _NOISE) and s.path:
                key = concept_key(_last_literal(s.path))
        elif s.kind is DocumentKind.MODEL:
            if s.resource is None:
                continue  # a bundle root ("A01 response 200") is not a concept
            key = concept_key(s.title.split(" / ")[-1])
        else:
            continue
        if key and key not in _NOISE:
            out[key].append(s)
    return out


@dataclass
class _ApiScan:
    groups: dict[str, list[DocumentSummary]]
    field_words: set[str]
    leaves: dict[str, set[str]]


def _difficulty(direct: int, present: int, total: int) -> tuple[str, str]:
    if direct == total:
        return ("ok", "Straightforward")
    if present == total:
        return ("warn", "Needs joins")
    return ("bad", f"Missing in {total - present} API(s)")


def _operations(docs: list[DocumentSummary]) -> set[str]:
    ops = set()
    for d in docs:
        if d.method == "GET":
            ops.add("read")
        elif d.method in _WRITE:
            ops.add("write")
    return ops or {"read"}


def _api_counts(docs: list[DocumentSummary], fields: int) -> ApiConceptCounts:
    endpoints = [d for d in docs if d.kind is DocumentKind.ENDPOINT]
    ops = {_OPERATION[d.method] for d in endpoints if d.method in _OPERATION}
    return ApiConceptCounts(
        models=sum(d.kind is DocumentKind.MODEL for d in docs),
        endpoints=len(endpoints),
        operations=tuple(o for o in ("read", "create", "update", "delete") if o in ops),
        fields=fields,
    )


def _n(count: int, word: str) -> str:
    return f"{count} {word}" + ("" if count == 1 else "s")


def _api_sentence(api: str, name: str, coverage: str, c: ApiConceptCounts) -> str:
    noun = name.lower()
    ops = f" ({', '.join(c.operations)})" if c.operations else ""
    if coverage == "absent":
        return f"{api} does not document {noun}"
    if coverage == "derived":
        return f"{api} has no {name} model or endpoint; only field names mention it"
    if c.models and c.endpoints:
        models = (
            f"an {name} model"
            if c.models == 1 and name[:1] in "AEIOU"
            else (f"a {name} model" if c.models == 1 else f"{c.models} {name} models")
        )
        return f"{api} has {models} and {_n(c.endpoints, noun + ' endpoint')}{ops}"
    if c.endpoints:
        return (
            f"{api} documents {noun} through {_n(c.endpoints, 'endpoint')}{ops} "
            f"but has no {name} model"
        )
    models = "a model" if c.models == 1 else f"{c.models} models"
    return f"{api} documents {name} as {models} but has no {noun} endpoint"


def build_reason(
    name: str,
    coverage: dict[str, str],
    counts: dict[str, ApiConceptCounts],
    labels: dict[str, str],
    likely_fields: int,
    difficulty: tuple[str, str],
) -> str:
    """One factual paragraph from the build's documents (no LLM, nothing invented)."""
    parts = [_api_sentence(labels[a], name, coverage[a], counts[a]) for a in coverage]
    text = "; ".join(parts) + "."
    text += f" About {_n(likely_fields, 'field')} {'is' if likely_fields == 1 else 'are'}"
    text += " likely to map."
    derived = [labels[a] for a, v in coverage.items() if v == "derived"]
    absent = [labels[a] for a, v in coverage.items() if v == "absent"]
    if difficulty[0] == "ok":
        text += f" {difficulty[1]} because every API documents {name} directly."
    elif difficulty[0] == "warn":
        text += f" {difficulty[1]} because {', '.join(derived)} only mention it in fields."
    else:
        text += f" {difficulty[1]}: {', '.join(absent)}."
    return text


def _matches(c: ConceptSuggestion, f: SuggestFilter) -> bool:
    if f.q:
        q = f.q.lower()
        if q not in c.name.lower() and q not in c.key and q not in c.reason.lower():
            return False
    return all(c.coverage.get(a, "absent") != "absent" for a in f.require)


class SuggestConcepts:
    def __init__(self, resolver: BuildResolver, index: SearchIndex, facts: FactIndex) -> None:
        self._resolver = resolver
        self._index = index
        self._facts = facts

    def _scan(self, r: ResolvedBuild, names: dict[str, str]) -> _ApiScan:
        summaries, _ = self._index.browse(r.build.build_id, (), None, 100_000, 0)
        groups = concept_docs(summaries)
        for key, docs in groups.items():
            # Prefer a document whose own name gives the key (a model "Order", an endpoint with
            # resource "Order"); else the key itself, title-cased ("orders" path -> "Order").
            for d in docs:
                own = (d.resource if d.kind is DocumentKind.ENDPOINT else d.title) or ""
                own = own.split(" / ")[-1]
                if concept_key(own) == key:
                    names.setdefault(key, own)
                    break
            names.setdefault(key, key.capitalize())
        owner_key = {d.doc_id: k for k, docs in groups.items() for d in docs}
        words: set[str] = set()
        leaves: dict[str, set[str]] = defaultdict(set)
        for f in self._facts.list_facts(r.build.build_id):
            if f.kind is not FactKind.FIELD:
                continue
            leaf = f.name.split(".")[-1].replace("[]", "")
            words.update(concept_key(part) for part in re.split(r"[_\-]", leaf.lower()))
            in_body = f.location is None or f.location.value in ("model", "response", "body")
            if f.owner_id in owner_key and in_body:
                leaves[owner_key[f.owner_id]].add(leaf.lower())
        return _ApiScan(groups, words, leaves)

    def _all(self, resolved: tuple[ResolvedBuild, ...]) -> list[ConceptSuggestion]:
        names: dict[str, str] = {}
        scans = {r.api.api_id.value: self._scan(r, names) for r in resolved}
        labels = {r.api.api_id.value: r.api.name for r in resolved}
        concepts: list[ConceptSuggestion] = []
        for key in sorted({k for sc in scans.values() for k in sc.groups}):
            coverage = {
                api: "direct"
                if key in sc.groups
                else "derived"
                if key in sc.field_words
                else "absent"
                for api, sc in scans.items()
            }
            present = [a for a, c in coverage.items() if c != "absent"]
            direct = [a for a, c in coverage.items() if c == "direct"]
            ops = _operations([d for a in direct for d in scans[a].groups[key]])
            fields = set().union(*(sc.leaves.get(key, set()) for sc in scans.values()))
            label = concept_label(names[key])
            counts = {
                a: _api_counts(sc.groups.get(key, []), len(sc.leaves.get(key, set())))
                for a, sc in scans.items()
            }
            difficulty = _difficulty(len(direct), len(present), len(scans))
            concepts.append(
                ConceptSuggestion(
                    key=key,
                    name=label,
                    reason=build_reason(label, coverage, counts, labels, len(fields), difficulty),
                    likely_fields=len(fields),
                    coverage=coverage,
                    operations=tuple(o for o in ("read", "write") if o in ops),
                    difficulty=difficulty,
                    doc_ids={
                        a: tuple(d.doc_id for d in sc.groups.get(key, []))
                        for a, sc in scans.items()
                    },
                    api_counts=counts,
                )
            )
        concepts.sort(
            key=lambda c: (
                -sum(v == "direct" for v in c.coverage.values()),
                -c.present,
                -c.likely_fields,
                c.key,
            )
        )
        return concepts

    def execute(self, apis: list[str], f: SuggestFilter | None = None) -> Suggestions:
        f = f or SuggestFilter()
        resolved = resolve_apis(self._resolver, apis)
        ids = [r.api.api_id.value for r in resolved]
        unknown = [a for a in f.require if a not in ids]
        if unknown:
            raise ModelInputError(f"require must be among the selected APIs: {unknown}")
        if f.only not in ("multi", "single", "all"):
            raise ModelInputError("only must be multi, single or all")
        limit = max(1, min(f.limit, MAX_LIMIT))
        offset = max(0, f.offset)
        matching = [c for c in self._all(resolved) if _matches(c, f)]
        multi = [c for c in matching if c.present >= 2]
        single = [c for c in matching if c.present == 1]
        chosen = {"multi": multi, "single": single, "all": multi + single}[f.only]
        if f.in_all:
            chosen = [c for c in chosen if c.in_all]
        if f.write_only:
            chosen = [c for c in chosen if c.writes]
        return Suggestions(
            apis=resolved,
            concepts=tuple(chosen[offset : offset + limit]),
            total=len(chosen),
            limit=limit,
            offset=offset,
            counts=SuggestCounts(
                all=len(multi),
                in_all=sum(c.in_all for c in multi),
                write=sum(c.writes for c in multi),
                single=len(single),
            ),
            not_modeled=len(single),
            not_modeled_examples=tuple(c.name for c in single[:8]),
        )
