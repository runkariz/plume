"""Score a canonical model against its model gold, per (gold field, API) cell.

Classes (stable; reports and the release gate key on them):

- ``correct``: a produced path is one of the expected paths (a dotted suffix counts:
  ``order.total_price`` = ``total_price``). Conversion, judged only for correct mappings (a
  structured ``conversion`` first, else the free-text ``transform``):
  ``conversion_missing`` (gold states a conversion, the mapping has no transform),
  ``conversion_wrong`` (the transform contradicts it: minor units where gold says decimal or the
  reverse, an enum value mapped to another target than gold's), else ok.
- ``wrong``: the produced path is a field of the API but not the expected one; or gold says the
  API has no such field and the model maps an existing field.
- ``invented``: the produced path is not a field of that API's pinned build.
- ``missed``: gold has a path and the model maps nothing.
- ``not_available_correct``: gold says not available and the model maps nothing.

A gold field is matched to a model field by name or alias (case, ``_``, ``-`` and spaces
ignored), children within matched parents; only when no field matches by name, a model field
that maps an expected path for that API counts as it. Model fields gold does not cover are not
scored, except that their invented paths still count as invented.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from plume.domain.models.canonical_model import (
    CanonicalField,
    Conversion,
    FieldSource,
    ModelDraft,
)
from plume.domain.models.model_gold import GoldCell, GoldModel
from plume.domain.models.release import GateFailure

CORRECT = "correct"
WRONG = "wrong"
INVENTED = "invented"
MISSED = "missed"
NOT_AVAILABLE_CORRECT = "not_available_correct"
CONVERSION_OK = "ok"
CONVERSION_MISSING = "conversion_missing"
CONVERSION_WRONG = "conversion_wrong"

FieldExists = Callable[[str, str], bool]  # (api, path) -> a documented field of its build?

_MINOR = re.compile(r"minor|cents?\b|smallest unit|[/÷x*]\s*100\b|\b100\s*[/÷]", re.I)
_PAIR = re.compile(r"['\"]?([\w.-]+)['\"]?\s*(?:->|→|=>|:|=)\s*['\"]?([\w.-]+)['\"]?")


def _key(name: str) -> str:
    return re.sub(r"[\s_\-]", "", name.lower())


def same_path(produced: str, expected: str) -> bool:
    a, b = produced.strip().lower(), expected.strip().lower()
    return a == b or a.endswith("." + b) or b.endswith("." + a)


@dataclass(frozen=True, slots=True)
class CellResult:
    field: str  # gold path
    api: str
    result: str
    expected: tuple[str, ...]
    produced: tuple[str, ...]
    conversion: str | None = None  # for correct cells whose gold states a conversion
    model_field: str | None = None  # the model path it was matched to
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class ModelEval:
    concept: str
    gold: str  # the gold file
    held_out: bool
    apis: tuple[str, ...]  # the APIs scored (gold's and the model's)
    cells: tuple[CellResult, ...]
    extra_invented: tuple[CellResult, ...] = ()  # invented paths of fields gold does not cover
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def invented(self) -> int:
        return self.counts.get(INVENTED, 0) + len(self.extra_invented)

    @property
    def precision(self) -> float | None:
        c = self.counts
        judged = c.get(CORRECT, 0) + c.get(WRONG, 0) + c.get(INVENTED, 0)
        return round(c.get(CORRECT, 0) / judged, 4) if judged else None

    @property
    def recall(self) -> float | None:
        expected = sum(1 for r in self.cells if r.expected)
        return round(self.counts.get(CORRECT, 0) / expected, 4) if expected else None

    def _rate(self, kind: str) -> float | None:
        correct = self.counts.get(CORRECT, 0)
        return round(self.counts.get(kind, 0) / correct, 4) if correct else None

    @property
    def conversion_missing_rate(self) -> float | None:
        return self._rate(CONVERSION_MISSING)

    @property
    def conversion_wrong_rate(self) -> float | None:
        return self._rate(CONVERSION_WRONG)

    def as_dict(self) -> dict[str, object]:
        def row(r: CellResult) -> dict[str, object]:
            return {
                "field": r.field,
                "api": r.api,
                "result": r.result,
                "expected": list(r.expected),
                "produced": list(r.produced),
                "conversion": r.conversion,
                "modelField": r.model_field,
                "detail": r.detail,
            }

        return {
            "concept": self.concept,
            "gold": self.gold,
            "heldOut": self.held_out,
            "apis": list(self.apis),
            "counts": dict(self.counts),
            "invented": self.invented,
            "precision": self.precision,
            "recall": self.recall,
            "conversionMissingRate": self.conversion_missing_rate,
            "conversionWrongRate": self.conversion_wrong_rate,
            "cells": [row(r) for r in self.cells],
            "extraInvented": [row(r) for r in self.extra_invented],
        }


def _align(draft: ModelDraft, gold: GoldModel) -> dict[str, tuple[str, CanonicalField]]:
    """Gold path -> (model path, model field), by name or alias within matched parents."""
    out: dict[str, tuple[str, CanonicalField]] = {}
    model_children: dict[str | None, list[tuple[str, CanonicalField]]] = {None: []}
    for path, f in draft.walk():
        parent = None
        for other_path, other in draft.walk():
            if any(f is c for c in other.fields):
                parent = other_path
                break
        model_children.setdefault(parent, []).append((path, f))
    for gold_path, gf, gold_parent in gold.walk():
        parent_model = out[gold_parent][0] if gold_parent and gold_parent in out else None
        if gold_parent and gold_parent not in out:
            continue  # the parent is unmatched: its children are matched by path only
        names = {_key(n) for n in gf.names}
        for path, f in model_children.get(parent_model, []):
            if _key(f.name) in names:
                out[gold_path] = (path, f)
                break
    return out


def _produced(src: FieldSource | None) -> tuple[str, ...]:
    return tuple(p.path for p in src.paths) if src is not None else ()


_MONEY = ("money-minor", "money-decimal", "money-decimal-string")


def _stated(conv: Conversion, said: Conversion) -> tuple[str, str | None]:
    """A structured conversion against gold's: minor vs decimal money, enum targets, kind."""
    if conv.kind in _MONEY and said.kind in _MONEY:
        if (conv.kind == "money-minor") != (said.kind == "money-minor"):
            return CONVERSION_WRONG, f"gold: {conv.kind}; the model states {said.kind}"
        return CONVERSION_OK, None
    if conv.kind == "enum" and conv.enum_map and said.enum_map:
        stated = {a.lower(): b for a, b in said.enum_map}
        bad = [
            f"{k} -> {stated[k.lower()]} (gold {v})"
            for k, v in conv.enum_map
            if k.lower() in stated and stated[k.lower()].lower() != v.lower()
        ]
        return (CONVERSION_WRONG, "; ".join(bad)) if bad else (CONVERSION_OK, None)
    if conv.kind not in ("other", said.kind) and said.kind != "other":
        return CONVERSION_WRONG, f"gold: {conv.kind}; the model states {said.kind}"
    return CONVERSION_OK, None


def _conversion(
    conv: Conversion, transform: str | None, said: Conversion | None = None
) -> tuple[str, str | None]:
    if said is not None:
        return _stated(conv, said)
    if not transform:
        return CONVERSION_MISSING, f"gold: {conv.kind}" + (f" ({conv.note})" if conv.note else "")
    if conv.kind in ("money-minor", "money-decimal", "money-decimal-string"):
        minor = bool(_MINOR.search(transform))
        if conv.kind == "money-minor" and not minor and re.search(r"decimal", transform, re.I):
            return CONVERSION_WRONG, "gold: minor units; the transform treats it as a decimal"
        if conv.kind != "money-minor" and minor:
            return CONVERSION_WRONG, "gold: a decimal amount; the transform converts minor units"
    if conv.kind == "enum" and conv.enum_map:
        pairs = {a.lower(): b for a, b in _PAIR.findall(transform)}
        bad = [
            f"{k} -> {pairs[k.lower()]} (gold {v})"
            for k, v in conv.enum_map
            if k.lower() in pairs and pairs[k.lower()].lower() != v.lower()
        ]
        if bad:
            return CONVERSION_WRONG, "; ".join(bad)
    return CONVERSION_OK, None


def _score_cell(
    gold_path: str,
    api: str,
    cell: GoldCell,
    matched: tuple[str, CanonicalField] | None,
    draft: ModelDraft,
    exists: FieldExists,
) -> CellResult:
    src = matched[1].source(api) if matched else None
    model_path = matched[0] if matched else None
    produced = _produced(src)
    if matched is None and cell.paths:
        for path, f in draft.walk():  # no field of that name: mapped under another name?
            other = f.source(api)
            if any(same_path(p, e) for p in _produced(other) for e in cell.paths):
                src, model_path, produced = other, path, _produced(other)
                break
    if not produced:
        result = NOT_AVAILABLE_CORRECT if cell.not_available else MISSED
        return CellResult(gold_path, api, result, cell.paths, (), model_field=model_path)
    if any(not exists(api, p) for p in produced):
        missing = [p for p in produced if not exists(api, p)]
        return CellResult(
            gold_path, api, INVENTED, cell.paths, produced, model_field=model_path,
            detail=f"not a field of {api}: {', '.join(missing)}",
        )  # fmt: skip
    if cell.not_available:
        return CellResult(
            gold_path, api, WRONG, (), produced, model_field=model_path,
            detail=f"gold: {api} has no such field" + (f" ({cell.note})" if cell.note else ""),
        )  # fmt: skip
    if not any(same_path(p, e) for p in produced for e in cell.paths):
        return CellResult(gold_path, api, WRONG, cell.paths, produced, model_field=model_path)
    conversion, detail = (
        _conversion(
            cell.conversion, src.transform if src else None, src.conversion if src else None
        )
        if cell.conversion
        else (None, None)
    )
    return CellResult(gold_path, api, CORRECT, cell.paths, produced, conversion, model_path, detail)


def score(
    draft: ModelDraft, gold: GoldModel, model_apis: tuple[str, ...], exists: FieldExists
) -> ModelEval:
    """Score ``draft`` (a model over ``model_apis``) against ``gold`` on the APIs both have."""
    apis = tuple(a for a in gold.apis if a in set(model_apis))
    aligned = _align(draft, gold)
    cells: list[CellResult] = []
    for gold_path, gf, _ in gold.walk():
        for api in apis:
            cell = gf.cell(api)
            if cell is not None:
                cells.append(
                    _score_cell(gold_path, api, cell, aligned.get(gold_path), draft, exists)
                )
    scored = {(r.model_field, r.api) for r in cells if r.model_field}
    extra = [
        CellResult(
            "",
            api,
            INVENTED,
            (),
            _produced(src),
            model_field=path,
            detail=f"not a field of {api}: {p.path}",
        )
        for path, f in draft.walk()
        for api, src in f.sources
        if api in apis and (path, api) not in scored
        for p in src.paths
        if not exists(api, p.path)
    ]
    counts: dict[str, int] = {}
    for r in cells:
        counts[r.result] = counts.get(r.result, 0) + 1
        if r.conversion in (CONVERSION_MISSING, CONVERSION_WRONG):
            counts[r.conversion] = counts.get(r.conversion, 0) + 1
    return ModelEval(
        gold.concept, gold.source, gold.held_out, apis, tuple(cells), tuple(extra), counts
    )


@dataclass(frozen=True, slots=True)
class ModelGatePolicy:
    """Releasing an official model: no invented field ever; recall at least ``min_recall`` once
    it is set (None until the first gold sets give a sensible threshold)."""

    min_recall: float | None = None

    def failures(self, result: ModelEval) -> list[GateFailure]:
        out = []
        if result.invented:
            rows = (*result.cells, *result.extra_invented)
            fields = sorted({r.field or r.model_field or "?" for r in rows if r.result == INVENTED})
            out.append(
                GateFailure(f"{result.invented} invented mapping(s): {', '.join(fields)}", False)
            )
        recall = result.recall
        if self.min_recall is not None and recall is not None and recall < self.min_recall:
            out.append(GateFailure(f"recall {recall} below {self.min_recall}", True))
        return out
