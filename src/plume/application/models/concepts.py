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

_NOISE = frozenset(
    {"general", "default", "misc", "other", "error", "errors", "api", "app", "data", "datum"}
)
_WRITE = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MAX_APIS = 6
MAX_CONCEPTS = 24


class ModelInputError(ApplicationError, ValueError):
    code = "invalid_input"


def concept_key(name: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    if key.endswith("ies") and len(key) > 4:
        key = key[:-3] + "y"
    elif key.endswith("s") and not key.endswith("ss") and len(key) > 3:
        key = key[:-1]
    return key


def concept_label(name: str) -> str:
    words = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).replace("_", " ").split()
    return " ".join(w.capitalize() for w in words) or name


@dataclass(frozen=True, slots=True)
class ConceptSuggestion:
    key: str
    name: str
    description: str
    likely_fields: int
    coverage: dict[str, str]  # api -> direct | derived | absent
    operations: tuple[str, ...]
    difficulty: tuple[str, str]  # (tone, label)
    doc_ids: dict[str, tuple[str, ...]]  # api -> documents of this concept


@dataclass(frozen=True, slots=True)
class Suggestions:
    apis: tuple[ResolvedBuild, ...]
    concepts: tuple[ConceptSuggestion, ...]
    not_modeled: int
    not_modeled_examples: tuple[str, ...]


def resolve_apis(resolver: BuildResolver, apis: list[str]) -> tuple[ResolvedBuild, ...]:
    unique = list(dict.fromkeys(a.strip() for a in apis if a.strip()))
    if not 2 <= len(unique) <= MAX_APIS:
        raise ModelInputError(f"pick 2..{MAX_APIS} different APIs")
    return tuple(resolver.resolve(a) for a in unique)


def _last_literal(path: str) -> str:
    """``/api/{version}/orders/{id}.json`` -> ``orders``."""
    for seg in reversed(path.strip("/").split("/")):
        if seg and "{" not in seg:
            return seg.split(".", 1)[0]
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

    def execute(self, apis: list[str]) -> Suggestions:
        resolved = resolve_apis(self._resolver, apis)
        names: dict[str, str] = {}
        scans = {r.api.api_id.value: self._scan(r, names) for r in resolved}
        api_ids = list(scans)
        concepts: list[ConceptSuggestion] = []
        single: list[str] = []
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
            if len(present) < 2 or not direct:
                single.append(concept_label(names[key]))
                continue
            ops = _operations([d for a in direct for d in scans[a].groups[key]])
            fields = set().union(*(sc.leaves.get(key, set()) for sc in scans.values()))
            label = concept_label(names[key])
            derived = sorted(set(present) - set(direct))
            description = f"{label} as documented by {', '.join(direct)}"
            if derived:
                description += f"; referenced by fields in {', '.join(derived)}"
            concepts.append(
                ConceptSuggestion(
                    key=key,
                    name=label,
                    description=description,
                    likely_fields=len(fields),
                    coverage=coverage,
                    operations=tuple(o for o in ("read", "write") if o in ops),
                    difficulty=_difficulty(len(direct), len(present), len(api_ids)),
                    doc_ids={
                        a: tuple(d.doc_id for d in sc.groups.get(key, []))
                        for a, sc in scans.items()
                    },
                )
            )
        concepts.sort(
            key=lambda c: (
                -sum(v == "direct" for v in c.coverage.values()),
                -sum(v != "absent" for v in c.coverage.values()),
                -c.likely_fields,
                c.key,
            )
        )
        return Suggestions(
            apis=resolved,
            concepts=tuple(concepts[:MAX_CONCEPTS]),
            not_modeled=len(single) + max(0, len(concepts) - MAX_CONCEPTS),
            not_modeled_examples=tuple(single[:8]),
        )
