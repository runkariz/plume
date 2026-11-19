"""Model gold: the expected mapping of a canonical concept across a group of APIs, approved by a
person, used to score generated models (``model_eval``) and to gate official releases.

File format ``plume.model-gold.v1`` (one concept, or several under ``models`` for a set)::

    {"schema": "plume.model-gold.v1", "concept": "Order", "group": "1",
     "apis": ["shopify", "woocommerce"], "heldOut": false, "builds": {"shopify": "b-..."},
     "fields": [
       {"name": "total", "aliases": ["total_price"], "type": "money", "required": true,
        "apis": {"shopify": {"paths": ["total_price"],
                             "conversion": {"kind": "money-decimal-string", "note": "..."}},
                 "woocommerce": {"notAvailable": true, "note": "..."}},
        "fields": [ ...sub-fields of an object / array field... ]}]}

A cell is one (field, API): expected paths (any of them is right), or ``notAvailable``. An API
missing from a field's ``apis`` is not judged. Gold content is for scoring only: the generator's
prompts and examples are never built from it.
"""

from dataclasses import dataclass
from typing import Any

from plume.domain.models.canonical_model import (
    Conversion,
    DraftFormatError,
    parse_conversion,
)
from plume.domain.shared.errors import DomainError

SCHEMA = "plume.model-gold.v1"


class GoldFormatError(DomainError, ValueError):
    """The model gold JSON does not have the expected shape."""


@dataclass(frozen=True, slots=True)
class GoldCell:
    paths: tuple[str, ...] = ()
    not_available: bool = False
    conversion: Conversion | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class GoldField:
    name: str
    aliases: tuple[str, ...]
    type: str | None
    required: bool
    cells: tuple[tuple[str, GoldCell], ...]  # (api, cell), sorted by api
    fields: tuple["GoldField", ...] = ()

    def cell(self, api: str) -> GoldCell | None:
        return dict(self.cells).get(api)

    @property
    def names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


@dataclass(frozen=True, slots=True)
class GoldModel:
    concept: str
    apis: tuple[str, ...]
    fields: tuple[GoldField, ...]
    group: str | None = None
    held_out: bool = False
    source: str = ""  # the file it came from

    def walk(self) -> list[tuple[str, GoldField, str | None]]:
        """Every field with its gold path and its parent's path, parents before children."""
        out: list[tuple[str, GoldField, str | None]] = []

        def visit(fields: tuple[GoldField, ...], prefix: str, parent: str | None) -> None:
            for f in fields:
                path = f"{prefix}.{f.name}" if prefix else f.name
                out.append((path, f, parent))
                visit(f.fields, path, path)

        visit(self.fields, "", None)
        return out


def _strs(value: Any, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise GoldFormatError(f"{where} must be a list of strings")
    return tuple(v.strip() for v in value if v.strip())


def _conversion(raw: Any, where: str) -> Conversion | None:
    try:
        return parse_conversion(raw, where)
    except DraftFormatError as exc:
        raise GoldFormatError(str(exc)) from exc


def _cell(raw: Any, where: str) -> GoldCell:
    if not isinstance(raw, dict):
        raise GoldFormatError(f"{where} must be an object")
    paths = _strs(raw.get("paths"), f"{where}.paths")
    not_available = raw.get("notAvailable") is True
    if bool(paths) == not_available:
        raise GoldFormatError(f"{where} needs either paths or notAvailable: true")
    note = raw.get("note")
    return GoldCell(
        paths,
        not_available,
        _conversion(raw.get("conversion"), where),
        note if isinstance(note, str) and note.strip() else None,
    )


def _field(raw: Any, where: str, apis: tuple[str, ...]) -> GoldField:
    if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"]:
        raise GoldFormatError(f"{where} must be an object with a name")
    name = raw["name"].strip()
    here = f"{where}({name})"
    cells_raw = raw.get("apis") or {}
    if not isinstance(cells_raw, dict):
        raise GoldFormatError(f"{here}.apis must be an object")
    unknown = sorted(set(cells_raw) - set(apis))
    if unknown:
        raise GoldFormatError(f"{here}.apis names APIs not in the gold's apis: {unknown}")
    subs = raw.get("fields") or []
    if not isinstance(subs, list):
        raise GoldFormatError(f"{here}.fields must be a list")
    kind = raw.get("type")
    return GoldField(
        name=name,
        aliases=_strs(raw.get("aliases"), f"{here}.aliases"),
        type=kind if isinstance(kind, str) else None,
        required=raw.get("required") is True,
        cells=tuple(sorted((a, _cell(c, f"{here}.apis.{a}")) for a, c in cells_raw.items())),
        fields=tuple(_field(s, f"{here}.fields[{i}]", apis) for i, s in enumerate(subs)),
    )


def _model(raw: Any, where: str, source: str, held_out: bool) -> GoldModel:
    if not isinstance(raw, dict) or not isinstance(raw.get("concept"), str):
        raise GoldFormatError(f"{where} must be an object with a concept")
    apis = _strs(raw.get("apis"), f"{where}.apis")
    if not apis:
        raise GoldFormatError(f"{where}.apis is empty")
    fields = raw.get("fields")
    if not isinstance(fields, list) or not fields:
        raise GoldFormatError(f"{where}.fields must be a non-empty list")
    group = raw.get("group")
    return GoldModel(
        concept=raw["concept"].strip(),
        apis=apis,
        fields=tuple(_field(f, f"{where}.fields[{i}]", apis) for i, f in enumerate(fields)),
        group=str(group) if group is not None else None,
        held_out=raw.get("heldOut") is True or held_out,
        source=source,
    )


def parse_gold(raw: Any, source: str = "") -> tuple[GoldModel, ...]:
    """A gold file: one concept, or several under ``models`` (a set). ``heldOut`` on the file
    applies to every model in it."""
    if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
        raise GoldFormatError(f"{source or 'gold'}: schema must be {SCHEMA}")
    held_out = raw.get("heldOut") is True
    if "models" in raw:
        models = raw["models"]
        if not isinstance(models, list) or not models:
            raise GoldFormatError(f"{source}: models must be a non-empty list")
        merged = [{"apis": raw.get("apis"), "group": raw.get("group"), **m} for m in models]
        return tuple(
            _model(m, f"{source}.models[{i}]", source, held_out) for i, m in enumerate(merged)
        )
    return (_model(raw, source or "gold", source, held_out),)
