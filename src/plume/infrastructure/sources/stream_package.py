"""Reads a connector package (``connector/`` + optional ``knowledge-export/``) into documents.

The reader depends only on the package's files, not on who produced it. Layout (contract
``package.json schemaVersion`` 1.x):

- ``connector/app.json``: name, summary, docLink, iconUrl, category, apiVersioning, errorFormat.
- ``connector/endpoints/<id>/request.json`` (+ ``params``/``variables``/``headers``/``body``
  schemas and ``responses/<status>.schema.json``).
- ``connector/models/<name>.schema.json`` (JSON schema; ``x-complete``, ``x-source-url``).
- ``connector/knowledge/<id>.json`` + ``<id>.md``: guide pages.
- ``connector/auth/<id>.json``: auth schemes and their scopes.
- ``knowledge-export/**/*.md`` (optional, Plume-only): cleaned page text, one guide per file.

``ref`` is a directory that contains ``connector/`` (or is the ``connector/`` folder itself).
"""

import hashlib
import itertools
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

from plume.application.errors import SourcePackageError
from plume.application.ports.package_source import SourcePackage
from plume.domain.knowledge import rate_limits
from plume.domain.knowledge.api import ApiId, ApiInfo, Category
from plume.domain.knowledge.asset import CONTENT_TYPES, ICON, MAX_ASSET_BYTES, Asset
from plume.domain.knowledge.document import (
    FIELDS_BOUNDED_KEY,
    RULE_SOURCES_KEY,
    TRIGGER_PAYLOAD_KEY,
    Document,
    DocumentKind,
    FieldLocation,
    FieldSpec,
    constraints_of,
    endpoint_doc_id,
    normalize_endpoint_path,
    real_path,
    slug_doc_id,
    url_path,
)
from plume.domain.knowledge.model_names import display_names, parse_bundled_title
from plume.domain.shared.errors import InvalidIdentifierError
from plume.infrastructure.sources import knowledge_export

JsonObj = dict[str, Any]
MAX_FIELD_DEPTH = 6
MAX_WALK_FIELDS = 2000  # per schema; the largest reference API (Magento orders) has 1422
SUPPORTED_CONTRACT_MAJOR = "1"
_TEMPLATE_VAR = re.compile(r"\{\{\s*(?:req_vars|vars)\.([A-Za-z0-9_]+)\s*\}\}")
_TEMPLATE_ANY = re.compile(r"\{\{[^}]*\}\}")
_SLUG = re.compile(r"[^a-z0-9._-]+")
_HASH_SKIP_PARTS = frozenset({".DS_Store"})


def _read_json(path: Path) -> JsonObj:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourcePackageError(f"cannot read {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise SourcePackageError(f"{path.name}: expected a JSON object")
    return data


def _opt_json(path: Path) -> JsonObj | None:
    return _read_json(path) if path.is_file() else None


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _slug(value: str) -> str:
    return _SLUG.sub("-", value.lower()).strip("-") or "x"


UNTYPED = "type not stated by the vendor"


def _type_of(schema: Mapping[str, Any]) -> str | None:
    """The stated type: ``type`` (nulls dropped), a ``$ref``'d schema's name, or for
    ``oneOf`` / ``anyOf`` its members' types ("string|integer", "Card|BankAccount") and for
    ``allOf`` its first typed member. None when the schema states none."""
    t = schema.get("type")
    if isinstance(t, list):
        names = [x for x in t if isinstance(x, str) and x != "null"]
        return "|".join(names) or None
    if isinstance(t, str):
        return t
    if "$ref" in schema and isinstance(schema["$ref"], str):
        return schema["$ref"].rsplit("/", 1)[-1].removesuffix(".schema.json")
    composed = _composed_type(schema)
    if composed is None and "properties" in schema:
        return "object"
    if composed is None and isinstance(schema.get("items"), dict):
        return "array"
    return composed


def _composed_type(schema: Mapping[str, Any]) -> str | None:
    for key in ("oneOf", "anyOf"):
        members = schema.get(key)
        if isinstance(members, list):
            types = [m_t for m in members if isinstance(m, dict) and (m_t := _type_of(m))]
            types = [x for x in dict.fromkeys(types) if x != "null"]
            if types:
                return "|".join(types)
    members = schema.get("allOf")
    if isinstance(members, list):
        return next((m_t for m in members if isinstance(m, dict) and (m_t := _type_of(m))), None)
    return None


@dataclass(frozen=True)
class _RefScope:
    """Where `$ref`s resolve: the current file's root schema and folder (None = no file refs)."""

    root: Mapping[str, Any]
    file: str
    folder: Path | None = None
    seen: frozenset[str] = frozenset()  # refs being expanded on this path (cycle guard)


def _model_of(schema: Mapping[str, Any], scope: _RefScope) -> str | None:
    """The model document a field's type refers to: a ``$ref`` (directly, as array items, or
    the single typed member of a composition) to an existing schema file in the package's
    models folder."""
    ref = schema.get("$ref")
    items = schema.get("items")
    if not isinstance(ref, str) and isinstance(items, dict):
        ref = items.get("$ref")
    if not isinstance(ref, str):
        for key in ("allOf", "oneOf", "anyOf"):
            refs = [m.get("$ref") for m in schema.get(key) or [] if isinstance(m, dict)]
            refs = [r for r in refs if isinstance(r, str)]
            if len(refs) == 1:
                ref = refs[0]
                break
    if not isinstance(ref, str) or scope.folder is None:
        return None
    file_part = ref.partition("#")[0]
    if not file_part.endswith(".schema.json"):
        return None
    path = (scope.folder / file_part).resolve()
    if not path.is_file() or path.parent.name != "models":
        return None
    return slug_doc_id(DocumentKind.MODEL, _slug(path.name.removesuffix(".schema.json")))


def _pointer_get(doc: Mapping[str, Any], pointer: str) -> Any:
    node: Any = doc
    for raw in [p for p in pointer.split("/") if p]:
        part = raw.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _resolve_ref(ref: str, scope: _RefScope) -> tuple[Mapping[str, Any], str, _RefScope] | None:
    """A `$ref` to the same file (`#/$defs/X`) or a sibling schema file
    (`orderlineitem.schema.json[#/...]`): the target schema, its pointer prefix (file#pointer)
    and the scope inside it. None when it can't be read or would loop."""
    file_part, _, fragment = ref.partition("#")
    key = f"{file_part or scope.file}#{fragment}"
    if key in scope.seen:
        return None
    if file_part:
        if scope.folder is None or "/" in file_part.replace("./", "") or ".." in file_part:
            return None  # only sibling files in the same folder
        path = scope.folder / file_part.removeprefix("./")
        if not path.is_file():
            return None
        root: Mapping[str, Any] = _read_json(path)
        inner = _RefScope(root, path.name, scope.folder, scope.seen | {key})
    else:
        root, inner = scope.root, replace(scope, seen=scope.seen | {key})
    target = _pointer_get(root, fragment) if fragment else root
    if not isinstance(target, dict):
        return None
    return target, f"{inner.file}#{fragment}", inner


def _walk_fields(
    schema: Mapping[str, Any],
    location: FieldLocation,
    pointer: str,
    prefix: str = "",
    depth: int = 0,
    scope: _RefScope | None = None,
    max_depth: int = MAX_FIELD_DEPTH,
) -> Iterator[FieldSpec]:
    """Every field of a schema as dotted paths (`line_items[].sku`). `$ref`s to the same file or
    to sibling schema files are followed (bounded depth, cycle-safe); a field found through a
    reference keeps that file in its pointer (`orderlineitem.schema.json#/properties/sku`)."""
    if depth > max_depth:
        return
    if scope is None:
        scope = _RefScope(schema, pointer.split("#", 1)[0])
    ref = schema.get("$ref")
    if isinstance(ref, str):
        resolved = _resolve_ref(ref, scope)
        if resolved is not None:
            target, target_pointer, inner = resolved
            yield from _walk_fields(
                target, location, target_pointer, prefix, depth, inner, max_depth
            )
        return
    props = schema.get("properties")
    raw_required = schema.get("required")
    required: list[Any] = raw_required if isinstance(raw_required, list) else []
    if isinstance(props, dict):
        for name, sub in props.items():
            if not isinstance(sub, dict):
                continue
            full = f"{prefix}.{name}" if prefix else name
            sub_pointer = f"{pointer}/properties/{name}"
            yield FieldSpec(
                name=full,
                location=location,
                type=_type_of(sub),
                required=name in required,
                description=_str(sub.get("description")) or _ref_description(sub, scope),
                pointer=sub_pointer,
                constraints=constraints_of(sub),
                model_id=_model_of(sub, scope),
            )
            yield from _walk_fields(sub, location, sub_pointer, full, depth + 1, scope, max_depth)
    items = schema.get("items")
    if isinstance(items, dict):
        yield from _walk_fields(
            items, location, f"{pointer}/items", f"{prefix}[]", depth + 1, scope, max_depth
        )


def _ref_description(sub: Mapping[str, Any], scope: _RefScope) -> str | None:
    """A field that is only a `$ref` (or an array of one) takes the referenced schema's
    description."""
    ref = sub.get("$ref")
    items = sub.get("items")
    if not isinstance(ref, str) and isinstance(items, dict):
        ref = items.get("$ref")
    if not isinstance(ref, str):
        return None
    resolved = _resolve_ref(ref, scope)
    return _str(resolved[0].get("description")) if resolved else None


def _bounded_fields(
    schema: Mapping[str, Any], location: FieldLocation, pointer: str, scope: _RefScope
) -> tuple[list[FieldSpec], int | None]:
    """The schema's fields, at most ``MAX_WALK_FIELDS``: the deepest nesting level whose fields
    fit (in the walk's order), and that level when it is not the full depth (else None).
    Schemas whose references fan out (an entity graph: order -> customer -> orders[] -> ...)
    would otherwise expand into hundreds of thousands of fields."""
    found: list[FieldSpec] = []
    for limit in range(MAX_FIELD_DEPTH, -1, -1):
        walk = _walk_fields(schema, location, pointer, scope=scope, max_depth=limit)
        found = list(itertools.islice(walk, MAX_WALK_FIELDS + 1))
        if len(found) <= MAX_WALK_FIELDS:
            return found, None if limit == MAX_FIELD_DEPTH else limit
    return found[:MAX_WALK_FIELDS], 0


def _bounded_note(level: int | None) -> str:
    if level is None:
        return ""
    return (
        f"Note: the schema has more than {MAX_WALK_FIELDS} fields; only fields up to nesting "
        f"level {level + 1} are listed here (the full schema is in the package)."
    )


_SHAPE_IGNORED = frozenset({"title", "description", "examples", "example", "default"})


def _shape_of(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {
            k: _shape_of(v)
            for k, v in sorted(schema.items())
            if k not in _SHAPE_IGNORED and not k.startswith("x-")
        }
    if isinstance(schema, list):
        return [_shape_of(v) for v in schema]
    return schema


def shape_hash(schema: Any) -> str:
    """Structure of a JSON schema, ignoring titles, descriptions, examples and x- keys."""
    canonical = json.dumps(_shape_of(schema), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _api_id(app: JsonObj, name: str) -> ApiId:
    """app.json `systemName` (Core's stable id) when present, else the slug of `name`."""
    system = _str(app.get("systemName"))
    if system is None:
        return ApiId.from_name(name)
    try:
        return ApiId(system.strip())
    except InvalidIdentifierError as exc:
        raise SourcePackageError(
            f"app.json systemName {system!r} is not a valid id (lower case, digits, inner "
            "dashes; max 64)"
        ) from exc


def display_name(name: str, texts: list[str]) -> str:
    """The product's own spelling: app.json ``name`` when it has capitals or spaces; for an
    all-lowercase id, the casing the package's own summary uses ("woocommerce" ->
    "WooCommerce"); else capitalised."""
    if name != name.lower() or " " in name.strip():
        return name
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", re.I)
    for text in texts:
        m = pattern.search(text)
        if m is not None and m.group(0) != name:
            return m.group(0)
    return name[:1].upper() + name[1:]


def _fields_section(title: str, fields: list[FieldSpec], level: int | None = None) -> str:
    if not fields:
        return ""
    lines = [f"## {title}"]
    if level is not None:
        lines.append(_bounded_note(level))
    for f in fields:
        bits = [f"`{f.name}`"]
        if f.type and f.model_id:
            bits.append(f"({f.type}, {f.model_id})")
        elif f.type:
            bits.append(f"({f.type})")
        elif f.location in (FieldLocation.MODEL, FieldLocation.RESPONSE, FieldLocation.BODY):
            bits.append(f"({UNTYPED})")
        if f.required:
            bits.append("required")
        line = " ".join(bits)
        if f.description:
            line += f": {f.description}"
        lines.append(f"- {line}")
    return "\n".join(lines)


def _obj(value: object) -> JsonObj:
    return value if isinstance(value, dict) else {}


# Include/partial tags a docs site expands when it renders a page (Markdoc, Liquid/Jekyll, Hugo,
# MDX): left in a package they mean the included content is missing.
_UNRESOLVED_INCLUDE = re.compile(
    r"\{%-?\s*(?:partial|include|include_relative|render)\b[^%]*%\}"
    r"|\{\{<\s*(?:include|readfile)\b[^>]*>\}\}"
    r"|<(?:Partial|Snippet|Include)\s+[^>]*/>"
)


def _flag_unresolved_includes(documents: list[Document], warnings: list[str]) -> list[Document]:
    """Flag documents that still contain include tags instead of the included content: marked
    incomplete (absence is then not proven) with a visible note, and a load warning."""
    out = []
    for d in documents:
        tags = _UNRESOLVED_INCLUDE.findall(d.text)
        if not tags:
            out.append(d)
            continue
        shown = ", ".join(t[:120] for t in tags[:3])
        warnings.append(f"{d.doc_id}: {len(tags)} unresolved include tag(s) ({shown})")
        note = (
            f"> Plume: this page contains {len(tags)} unresolved include tag(s) ({shown}); "
            "the included content is not in the package."
        )
        out.append(replace(d, text=f"{note}\n\n{d.text}", complete=False))
    return out


def _json_files(folder: Path) -> list[JsonObj]:
    """Every *.json in a folder, verbatim, in name order ([] when the folder is absent)."""
    return [_read_json(p) for p in sorted(folder.glob("*.json"))] if folder.is_dir() else []


def _mcp_section(folder: Path) -> JsonObj | None:
    """connector/mcp/ (package 1.2, only when the vendor runs an MCP server), verbatim:
    servers/<id>.json, tools/<server>/<tool>/tool.json + input/output schemas."""
    servers_dir = folder / "servers"
    if not servers_dir.is_dir():
        return None
    servers = []
    for path in sorted(servers_dir.glob("*.json")):
        tools = []
        for tool_dir in sorted((folder / "tools" / path.stem).glob("*/")):
            tool = _opt_json(tool_dir / "tool.json")
            if tool is None:
                continue
            tools.append(
                {
                    "tool": tool,
                    "input_schema": _opt_json(tool_dir / "input.schema.json"),
                    "output_schema": _opt_json(tool_dir / "output.schema.json"),
                }
            )
        servers.append({"id": path.stem, "server": _read_json(path), "tools": tools})
    return {"servers": servers}


def _tags(req: JsonObj) -> tuple[str, ...]:
    """request.json tags[].name, verbatim and in order."""
    names = [t.get("name") for t in req.get("tags") or [] if isinstance(t, dict)]
    return tuple(dict.fromkeys(n for n in names if isinstance(n, str) and n))


def _url_path(url: str) -> str:
    return url_path(url)


_REQUEST_SCHEMAS = (
    ("variablesContractRef", FieldLocation.PATH, "Path parameters"),
    ("paramsContractRef", FieldLocation.QUERY, "Query parameters"),
    ("headersContractRef", FieldLocation.HEADER, "Headers"),
    ("bodyContractRef", FieldLocation.BODY, "Request body"),
)


def _endpoint_fields(
    folder: Path, req: JsonObj
) -> tuple[dict[str, list[FieldSpec]], list[FieldSpec], dict[str, int]]:
    """Request fields per section, 2xx response fields, and the sections whose fields were
    bounded (title -> listed nesting level)."""
    sections: dict[str, list[FieldSpec]] = {}
    bounded: dict[str, int] = {}
    for ref_key, location, title in _REQUEST_SCHEMAS:
        ref = _str(req.get(ref_key))
        data = _opt_json(folder / ref) if ref else None
        if data is not None and ref is not None:
            scope = _RefScope(data, ref, (folder / ref).parent)
            sections[title], level = _bounded_fields(data, location, f"{ref}#", scope)
            if level is not None:
                bounded[title] = level
    response_fields: list[FieldSpec] = []
    for response in req.get("responses") or []:
        status = response.get("statusCode") if isinstance(response, dict) else None
        ref = _str(response.get("contentContractRef")) if isinstance(response, dict) else None
        if ref and isinstance(status, int) and 200 <= status < 300:
            data = _opt_json(folder / ref)
            if data is not None:
                scope = _RefScope(data, ref, (folder / ref).parent)
                found, level = _bounded_fields(data, FieldLocation.RESPONSE, f"{ref}#", scope)
                response_fields.extend(found)
                if level is not None:
                    bounded["Response fields"] = min(level, bounded.get("Response fields", level))
    return sections, response_fields, bounded


def _required_scopes(req: JsonObj) -> tuple[str, ...]:
    scopes: list[str] = []
    for entry in req.get("requiredScopes") or []:
        if isinstance(entry, dict):
            scopes.extend(s for s in entry.get("scopes", []) if isinstance(s, str))
    return tuple(dict.fromkeys(scopes))


def _bullets(title: str, lines: list[str]) -> str:
    return f"## {title}\n" + "\n".join(lines) if lines else ""


def _endpoint_text(
    req: JsonObj,
    name: str,
    signature: str,
    sections: dict[str, list[FieldSpec]],
    response_fields: list[FieldSpec],
    scopes: tuple[str, ...],
    deprecated: bool,
    bounded: dict[str, int] | None = None,
) -> str:
    bounded = bounded or {}
    meta = [f"`{signature}`"]
    for label, key in (("Resource", "resource"), ("Operation", "operationKind")):
        if _str(req.get(key)):
            meta.append(f"{label}: {req[key]}")
    effects = [e for e in req.get("sideEffects") or [] if isinstance(e, str)]
    if effects:
        meta.append("Side effects: " + ", ".join(effects))
    if deprecated:
        meta.append("DEPRECATED")
    parts = [f"# {name}", " | ".join(meta)]
    description = _str(req.get("description")) or _str(req.get("summary"))
    if description:
        parts.append(description)
    if _str(req.get("permissionNote")):
        parts.append(f"Permission: {req['permissionNote']}")
    parts.append(_bullets("Required scopes", [f"- `{s}`" for s in scopes]))
    for _, _, title in _REQUEST_SCHEMAS:
        parts.append(_fields_section(title, sections.get(title, []), bounded.get(title)))
    responses = [r for r in req.get("responses") or [] if isinstance(r, dict)]
    parts.append(
        _bullets(
            "Responses",
            [
                f"- {r.get('statusCode')}"
                + (f" ({r['contentType']})" if r.get("contentType") else "")
                for r in responses
            ],
        )
    )
    parts.append(
        _fields_section("Response fields", response_fields, bounded.get("Response fields"))
    )
    errors = [e for e in req.get("errors") or [] if isinstance(e, dict)]
    parts.append(
        _bullets("Errors", [f"- {e.get('status')}: {e.get('meaning', '')}" for e in errors])
    )
    pagination = _obj(req.get("pagination"))
    parts.append(_bullets("Pagination", [f"- {k}: {v}" for k, v in sorted(pagination.items())]))
    rules = [r for r in req.get("businessRules") or [] if isinstance(r, str)]
    parts.append(_bullets("Business rules", [f"- {r}" for r in rules]))
    return "\n\n".join(p for p in parts if p)


class StreamPackageSource:
    """``PackageSource`` for a connector package directory."""

    def load(self, ref: str) -> SourcePackage:
        root = Path(ref).expanduser().resolve()
        connector = root if (root / "app.json").is_file() else root / "connector"
        if not (connector / "app.json").is_file():
            raise SourcePackageError(f"{ref}: no connector/app.json")
        package_root = connector.parent if connector.name == "connector" else connector
        warnings: list[str] = []

        contract = _opt_json(connector / "package.json") or {}
        contract_version = _str(contract.get("schemaVersion"))
        if contract_version and contract_version.split(".")[0] != SUPPORTED_CONTRACT_MAJOR:
            raise SourcePackageError(f"unsupported package schemaVersion {contract_version}")

        app = _read_json(connector / "app.json")
        info = self._api_info(app)
        versions = info.versions

        app_doc = self._app_document(info, app)
        env_schema = _opt_json(connector / "environment.variables.schema.json")
        app_doc = replace(
            app_doc,
            raw={
                "app": app,
                "environment_variables_schema": env_schema,
                "webhooks": _json_files(connector / "triggers" / "webhooks"),
                "mcp": _mcp_section(connector / "mcp"),
            },
        )
        documents: list[Document] = [app_doc]
        seen: set[str] = {documents[0].doc_id}

        def add(doc: Document, origin: str) -> None:
            if doc.doc_id in seen:
                warnings.append(f"duplicate document id {doc.doc_id} ({origin}); kept the first")
                return
            seen.add(doc.doc_id)
            documents.append(doc)

        versioning = app.get("apiVersioning")
        rolling = isinstance(versioning, dict) and bool(versioning.get("releaseCadence"))
        limits = rate_limits.groups(app)
        endpoints = [
            (
                folder,
                self._endpoint(
                    folder, _read_json(folder / "request.json"), versions, rolling, limits
                ),
            )
            for folder in sorted((connector / "endpoints").glob("*/"))
            if (folder / "request.json").is_file()
        ]
        for doc, origin in _distinct_endpoint_ids(endpoints):
            add(doc, origin)
        returned_by = _response_titles(connector, versions)
        for model in self._models(connector):
            add(_with_operations(model, returned_by), model.doc_id)
        for doc, origin in self._guides_and_auth(connector, warnings):
            add(doc, origin)
        for path in sorted((connector / "triggers" / "events").glob("*.json")):
            if not _COMPANION.match(path.name):  # <event>.payload.{schema,sample}.json
                add(self._trigger(path), path.name)
        documents = _attach_payloads(documents, connector, warnings)
        icon, extra_hashed = self._icon(connector, package_root)
        export = package_root / "knowledge-export"
        if export.is_dir() and knowledge_export.detect(export):
            documents = _apply_export(
                documents, knowledge_export.load(export), warnings, info.versions
            )
        elif export.is_dir():
            for path in sorted(export.rglob("*.md")):
                add(self._export_page(path, export), str(path.relative_to(export)))

        if export.is_dir():
            documents = _merge_unit_links(
                documents, knowledge_export.load_unit_links(export), warnings
            )
        documents = _link_documents(documents, warnings, info.versions)
        documents = _flag_unresolved_includes(documents, warnings)
        manifest = _opt_json(package_root / "manifest.json") or {}
        produced = manifest.get("warnings")
        if isinstance(produced, list):  # the producer's own warnings, on the app document
            app_index = next(i for i, d in enumerate(documents) if d.kind is DocumentKind.APP)
            app_raw = {**(documents[app_index].raw or {}), "package_warnings": produced}
            documents[app_index] = replace(documents[app_index], raw=app_raw)
        return SourcePackage(
            api=info,
            documents=tuple(documents),
            package_hash=self._hash(
                connector,
                export if export.is_dir() else None,
                extra_hashed,
                produced if isinstance(produced, list) else None,
            ),
            source_ref=str(package_root),
            run_id=_str(manifest.get("runId")),
            contract_version=contract_version,
            warnings=tuple(warnings),
            assets=(icon,) if icon is not None else (),
        )

    # -- pieces --------------------------------------------------------------------------------

    @staticmethod
    def _hash(
        connector: Path,
        export: Path | None,
        extra: list[Path] | None = None,
        manifest_warnings: list[Any] | None = None,
    ) -> str:
        """The bytes Plume reads. Of manifest.json only its warnings count (run ids and
        timestamps do not); a package without warnings hashes as before."""
        digest = hashlib.sha256()
        if manifest_warnings:
            digest.update(b"manifest/warnings\0")
            digest.update(json.dumps(manifest_warnings, sort_keys=True).encode())
        for path in extra or []:  # files outside connector/ that Plume reads (e.g. _icon/)
            digest.update(f"extra/{path.name}\0".encode())
            digest.update(path.read_bytes())
        for base, label in ((connector, "connector"), (export, "knowledge-export")):
            if base is None:
                continue
            for path in sorted(p for p in base.rglob("*") if p.is_file()):
                if path.name in _HASH_SKIP_PARTS:
                    continue
                digest.update(f"{label}/{path.relative_to(base).as_posix()}\0".encode())
                digest.update(path.read_bytes())
                digest.update(b"\0")
        return f"sha256:{digest.hexdigest()}"

    @staticmethod
    def _api_info(app: JsonObj) -> ApiInfo:
        name = _str(app.get("name"))
        if name is None:
            raise SourcePackageError("app.json has no name")
        versioning = _obj(app.get("apiVersioning"))
        versions = tuple(v for v in versioning.get("versions", []) if isinstance(v, str))
        cat = app.get("category")
        category = None
        if isinstance(cat, dict) and _str(cat.get("key")):
            confidence = cat.get("confidence")
            bundle = cat.get("bundleVersion")
            category = Category(
                key=str(cat["key"]),
                reason=_str(cat.get("reason")),
                confidence=float(confidence) if isinstance(confidence, int | float) else None,
                bundle_version=bundle if isinstance(bundle, int) else None,
            )
        summary = _str(app.get("summary")) or _str(app.get("description")) or ""
        api_id = _api_id(app, name)
        # Core's convention: `name` is the display name, `systemName` the stable id.
        title = (
            _str(app.get("title"))
            or _str(app.get("displayName"))
            or (name if _str(app.get("systemName")) and name != api_id.value else None)
        )
        return ApiInfo(
            api_id=api_id,
            name=title or display_name(name, [summary, _str(app.get("description")) or ""]),
            name_source="package" if title else "derived",
            summary=summary,
            doc_link=_str(app.get("docLink")),
            icon_url=_str(app.get("iconUrl")),
            category=category,
            versions=versions,
        )

    @staticmethod
    def _app_document(info: ApiInfo, app: JsonObj) -> Document:
        parts = [f"# {info.name}"]
        if info.summary:
            parts.append(info.summary)
        if info.category:
            parts.append(f"Category: {info.category.key}")
        if info.versions:
            parts.append("API versions: " + ", ".join(info.versions))
        base_urls = [u for u in app.get("baseUrls", []) if isinstance(u, str)]
        if base_urls:
            parts.append("Base URLs: " + ", ".join(base_urls))
        error_format = app.get("errorFormat")
        if isinstance(error_format, dict):
            lines = ["## Errors"]
            if _str(error_format.get("notes")):
                lines.append(str(error_format["notes"]))
            for code in error_format.get("statusCodes", []):
                if isinstance(code, dict):
                    lines.append(f"- {code.get('status')}: {code.get('meaning', '')}")
            parts.append("\n".join(lines))
        return Document(
            doc_id=slug_doc_id(DocumentKind.APP, info.api_id.value),
            kind=DocumentKind.APP,
            title=info.name,
            text="\n\n".join(parts),
            source_url=info.doc_link,
        )

    @staticmethod
    def _endpoint(
        folder: Path,
        req: JsonObj,
        versions: tuple[str, ...],
        rolling: bool = False,
        limits: list[dict[str, Any]] | None = None,
    ) -> Document:
        method = _str(req.get("method"))
        url = _str(req.get("url"))
        if method is None or url is None:
            raise SourcePackageError(f"endpoint {folder.name}: method and url are required")
        path = normalize_endpoint_path(_url_path(url), versions)
        method = method.upper()
        name = _str(req.get("name")) or f"{method} {path}"
        sections, response_fields, bounded = _endpoint_fields(folder, req)
        scopes = _required_scopes(req)
        deprecated = bool(req.get("isDeprecated")) or bool(req.get("deprecation"))
        provenance = _obj(req.get("provenance"))
        # realPath, rate limit and field constraints are kept on the document (fields, facts,
        # payloads), NOT in its text: the text is what is embedded, and adding them cost
        # recall on the frozen gold sets (Shopify -2.5, Woo -2.7 points at recall@5).
        fixed = real_path(req, path, rolling)
        limit = rate_limits.resolve(req, limits or [])
        return Document(
            doc_id=endpoint_doc_id(method, path),
            kind=DocumentKind.ENDPOINT,
            title=name,
            text=_endpoint_text(
                req,
                name,
                f"{method} {path}",
                sections,
                response_fields,
                scopes,
                deprecated,
                bounded,
            ),
            source_url=_str(provenance.get("sourceUrl")) or _str(req.get("docLink")),
            anchor=doc_anchor(provenance.get("docAnchor")),
            resource=_str(req.get("resource")),
            method=method,
            path=path,
            deprecated=deprecated,
            fields=tuple(f for fs in sections.values() for f in fs) + tuple(response_fields),
            scopes=scopes,
            source_id=_str(req.get("endpointId")),
            tags=_tags(req),
            raw=req if not bounded else {**req, FIELDS_BOUNDED_KEY: min(bounded.values()) + 1},
            real_path=fixed,
            rate_limit=limit,
        )

    def _guides_and_auth(self, connector: Path, warnings: list[str]) -> list[tuple[Document, str]]:
        out: list[tuple[Document, str]] = []
        for path in sorted((connector / "knowledge").glob("*.json")):
            doc = self._guide(path)
            if doc is not None:
                out.append((doc, path.name))
            else:
                warnings.append(f"knowledge {path.stem}: no markdown body, skipped")
        for path in sorted((connector / "auth").glob("*.json")):
            if not _COMPANION.match(path.name):  # <scheme>.<suffix>.{sample,schema}.json
                out.append((self._auth(path), path.name))
        return out

    def _models(self, connector: Path) -> list[Document]:
        """Models, with readable names for bundler-generated titles."""
        models = [self._model(p) for p in sorted((connector / "models").glob("*.schema.json"))]
        names = display_names((m.doc_id, m.title, m.shape) for m in models)
        return [_renamed(m, names[m.doc_id]) if m.doc_id in names else m for m in models]

    @staticmethod
    def _model(path: Path) -> Document:
        data = _read_json(path)
        stem = path.name.removesuffix(".schema.json")
        title = _str(data.get("title")) or stem
        fields, level = _bounded_fields(
            data, FieldLocation.MODEL, f"{path.name}#", _RefScope(data, path.name, path.parent)
        )
        complete = data.get("x-complete") is not False
        parts = [f"# {title} (model)"]
        if _str(data.get("description")):
            parts.append(str(data["description"]))
        if not complete:
            parts.append("Note: the source marks this model as incomplete.")
        section = _fields_section("Fields", fields, level)
        if section:
            parts.append(section)
        return Document(
            doc_id=slug_doc_id(DocumentKind.MODEL, _slug(stem)),
            kind=DocumentKind.MODEL,
            title=title,
            text="\n\n".join(parts),
            source_url=_str(data.get("x-source-url")),
            resource=title,
            complete=complete,
            fields=tuple(fields),
            source_id=title,
            shape=shape_hash(data),
            raw=data if level is None else {**data, FIELDS_BOUNDED_KEY: level + 1},
        )

    @staticmethod
    def _guide(path: Path) -> Document | None:
        meta = _read_json(path)
        body_path = path.with_suffix(".md")
        if not body_path.is_file():
            return None
        body = body_path.read_text(encoding="utf-8-sig")
        key = _str(meta.get("id")) or path.stem
        title = _str(meta.get("title")) or key
        linked = _unit_endpoint_ids(meta)
        return Document(
            doc_id=slug_doc_id(DocumentKind.GUIDE, _slug(key)),
            kind=DocumentKind.GUIDE,
            title=title,
            text=body.strip() or title,
            source_url=_str(meta.get("sourceUrl")),
            source_id=key,
            # resolved to endpoint document ids by _link_documents once all endpoints are read;
            # the unit's own links are "text" links (knowledge-export/unit-links.json adds more)
            raw={"endpointIds": linked, "linkBasis": dict.fromkeys(linked, CONNECTOR_BASIS)}
            if linked
            else None,
        )

    @staticmethod
    def _auth(path: Path) -> Document:
        data = _read_json(path)
        key = _str(data.get("id")) or path.stem
        title = _str(data.get("name")) or key
        parts = [f"# {title} (authentication)"]
        for label, field_name in (
            ("Type", "authorizationType"),
            ("Grant", "grantType"),
            ("Header", "headerName"),
        ):
            if _str(data.get(field_name)):
                parts.append(f"{label}: {data[field_name]}")
        scopes: list[str] = []
        lines = []
        for entry in data.get("scopes", []) or []:
            if isinstance(entry, dict) and _str(entry.get("scope")):
                scopes.append(str(entry["scope"]))
                desc = _str(entry.get("description"))
                lines.append(f"- `{entry['scope']}`" + (f": {desc}" if desc else ""))
        if lines:
            parts.append("## Scopes\n" + "\n".join(lines))
        ref = _str(data.get("variableContractRef")) or f"auth/{path.stem}.variables.schema.json"
        variables_path = path.parent.parent / ref
        if not variables_path.is_file():
            variables_path = path.with_name(f"{path.stem}.variables.schema.json")
        variables = _opt_json(variables_path)
        return Document(
            doc_id=slug_doc_id(DocumentKind.AUTH, _slug(key)),
            kind=DocumentKind.AUTH,
            title=title,
            text="\n\n".join(parts),
            scopes=tuple(dict.fromkeys(scopes)),
            source_id=key,
            raw={
                "scheme": data,
                "variables_schema": variables,
                "file": path.name,
                "companions": _companions(path),
            },
        )

    @staticmethod
    def _trigger(path: Path) -> Document:
        data = _read_json(path)
        key = _str(data.get("key")) or path.stem
        title = _str(data.get("title")) or key
        parts = [f"# {title} (trigger)", f"Key: `{key}`"]
        for label, name in (("Delivery", "delivery"), ("Resource", "resource")):
            if _str(data.get(name)):
                parts.append(f"{label}: {data[name]}")
        if _str(data.get("description")):
            parts.append(str(data["description"]))
        provenance = _obj(data.get("provenance"))
        return Document(
            doc_id=slug_doc_id(DocumentKind.TRIGGER, _slug(key.replace("/", "-"))),
            kind=DocumentKind.TRIGGER,
            title=title,
            text="\n\n".join(parts),
            source_url=_str(provenance.get("evidenceUrl")) or _str(data.get("sourceUrl")),
            resource=_str(data.get("resource")),
            source_id=key,
            raw=data,
        )

    @staticmethod
    def _icon(connector: Path, package_root: Path) -> tuple[Asset | None, list[Path]]:
        """The package's own icon: connector/icon.*, else _icon/icon.* (with pick.json)."""
        for folder in (connector, package_root / "_icon"):
            for ext, content_type in CONTENT_TYPES.items():
                path = folder / f"icon.{ext}"
                if path.is_file() and 0 < path.stat().st_size <= MAX_ASSET_BYTES:
                    rel = path.relative_to(package_root).as_posix()
                    hashed = [] if folder == connector else [path]
                    return Asset(ICON, content_type, path.read_bytes(), rel), hashed
        return None, []

    @staticmethod
    def _export_page(path: Path, base: Path) -> Document:
        text = path.read_text(encoding="utf-8-sig")
        source_url = None
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end != -1:
                for line in text[4:end].splitlines():
                    key, _, value = line.partition(":")
                    if key.strip() in {"source_url", "sourceUrl", "url"}:
                        source_url = value.strip() or None
                text = text[end + 4 :].lstrip("\n")
        heading = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), None)
        rel = path.relative_to(base).with_suffix("").as_posix()
        return Document(
            doc_id=slug_doc_id(DocumentKind.GUIDE, "export-" + _slug(rel.replace("/", "-"))),
            kind=DocumentKind.GUIDE,
            title=heading or rel,
            text=text.strip() or rel,
            source_url=source_url,
            source_id=rel,
        )


def _distinct_endpoint_ids(
    endpoints: list[tuple[Path, Document]],
) -> list[tuple[Document, str]]:
    """Operations that share METHOD + path (Mirakl's OF54 / OR15 / TL05 all GET /{file_path}:
    a URL taken from response data) stay distinct: each gets ``<id>@<package endpoint id>``
    (``@`` is safe in a URL path segment, ``#`` is not),
    stable across builds and independent of order."""
    count: dict[str, int] = {}
    for _, d in endpoints:
        count[d.doc_id] = count.get(d.doc_id, 0) + 1
    out = []
    for folder, d in endpoints:
        key = _slug(d.source_id or folder.name)
        out.append(
            (replace(d, doc_id=f"{d.doc_id}@{key}") if count[d.doc_id] > 1 else d, folder.name)
        )
    return out


# Files next to an auth scheme that describe it (variables, OAuth token request params, …):
# <scheme>.<suffix>.sample.json / <scheme>.<suffix>.schema.json. Never schemes of their own.
_COMPANION = re.compile(
    r"^(?P<scheme>[^.]+)\.(?P<suffix>[A-Za-z0-9_-]+)\.(?P<part>sample|schema)\.json$"
)


def _companions(scheme_path: Path) -> dict[str, dict[str, Any]]:
    """{suffix: {"schema": …, "sample": …}} of an auth scheme's companion files (verbatim)."""
    out: dict[str, dict[str, Any]] = {}
    for f in sorted(scheme_path.parent.glob(f"{scheme_path.stem}.*.json")):
        m = _COMPANION.match(f.name)
        if m and m["scheme"] == scheme_path.stem:
            out.setdefault(m["suffix"], {})[m["part"]] = _opt_json(f)
    return out


def _title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())


def _titles(node: Any, out: set[str]) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("title"), str):
            out.add(_title_key(node["title"]))
        for v in node.values():
            _titles(v, out)
    elif isinstance(node, list):
        for v in node:
            _titles(v, out)


def _response_titles(connector: Path, versions: tuple[str, ...]) -> dict[str, list[str]]:
    """Schema title -> the endpoints whose 2xx response schema names it (a bundled Mirakl
    "P11_Response_200_Products" is what GET /api/products/offers returns)."""
    out: dict[str, list[str]] = {}
    for folder in sorted((connector / "endpoints").glob("*/")):
        req = _opt_json(folder / "request.json")
        if not req or not _str(req.get("method")) or not _str(req.get("url")):
            continue
        doc_id = endpoint_doc_id(
            str(req["method"]).upper(),
            normalize_endpoint_path(_url_path(str(req["url"])), versions),
        )
        found: set[str] = set()
        for response in req.get("responses") or []:
            if not isinstance(response, dict):
                continue
            status, ref = response.get("statusCode"), _str(response.get("contentContractRef"))
            if ref and isinstance(status, int) and 200 <= status < 300:
                _titles(_opt_json(folder / ref), found)
        for t in found:
            out.setdefault(t, []).append(doc_id)
    return out


MAX_RETURNED_BY = 5  # a title in more responses than this says nothing


def _with_operations(model: Document, returned_by: dict[str, list[str]]) -> Document:
    """Record the operations that return a model, when the package says so by title."""
    title = model.source_id or model.title
    if parse_bundled_title(title) is None:  # only bundled names (P11_Response_200_…) say which
        return model
    ops = returned_by.get(_title_key(title), [])
    if not ops or len(ops) > MAX_RETURNED_BY or not isinstance(model.raw, dict):
        return model
    ops = sorted(ops, key=lambda d: (not d.startswith("endpoint:GET~"), d))
    return replace(model, raw={**model.raw, "x-plume-returned-by": ops})


def _renamed(model: Document, name: str) -> Document:
    """A bundler-titled model under its display name; the vendor title stays as source_id.

    A bundle root (a whole response/request body) gets no resource: it is not a concept."""
    original = model.title
    parsed = parse_bundled_title(original)
    resource = None if parsed is not None and parsed.is_root else name
    body = model.text.split("\n\n", 1)[1] if "\n\n" in model.text else ""
    text = f"# {name} (model)\n\nSource title: {original}" + (f"\n\n{body}" if body else "")
    return replace(model, title=name, resource=resource, text=text, source_id=original)


MAX_REFS_SHOWN = 5


def _ref_path(connector: Path, ref: str) -> Path | None:
    """A payload/sample ref as a file inside the connector: relative to triggers/events/ (the
    stream contract), else to the connector root. None when missing or outside the connector."""
    events = connector / "triggers" / "events"
    root = connector.resolve()
    for base in (events, connector):
        path = (base / ref).resolve()
        if path.is_file() and path.is_relative_to(root):
            return path
    return None


def _model_ref(connector: Path, ref: str, schema: JsonObj | None) -> str | None:
    """The model a payload ref names: ``model:<name>``, a file in connector/models/, or a
    payload schema that is only a ``$ref`` to one. None when it is not a model ref."""
    if ref.startswith("model:"):
        return model_key(ref.removeprefix("model:").strip())
    models = (connector / "models").resolve()
    targets = [ref]
    only_ref = schema is not None and not set(schema) - {"$ref", "title", "description", "$schema"}
    if schema is not None and only_ref and isinstance(schema.get("$ref"), str):
        targets.append(str(schema["$ref"]).partition("#")[0])
    for target in targets:
        path = _ref_path(connector, target) if target else None
        if path is not None and path.parent == models and path.name.endswith(".schema.json"):
            return model_key(path.name.removesuffix(".schema.json"))
    return None


def _payload_of(
    doc: Document, connector: Path, model_ids: dict[str, Document], missing: list[str]
) -> Document:
    """A trigger with its payload resolved: the schema's fields (rendered like a model's), or a
    link to the connector model it names, plus the sample. Unresolvable refs go to `missing`."""
    data = dict(doc.raw or {})
    schema_ref = _str(data.get("payloadSchemaRef"))
    sample_ref = _str(data.get("sampleRef"))
    if schema_ref is None and sample_ref is None:
        return doc
    schema: JsonObj | None = None
    model: Document | None = None
    fields: list[FieldSpec] = []
    if schema_ref is not None:
        path = None if schema_ref.startswith("model:") else _ref_path(connector, schema_ref)
        if path is not None:
            try:
                schema = _read_json(path)
            except SourcePackageError:
                path = None
        model_id = _model_ref(connector, schema_ref, schema)
        model = model_ids.get(model_id) if model_id else None
        if model is not None:
            schema = None  # link the model instead of repeating its fields
        elif schema is not None and path is not None:
            fields, _ = _bounded_fields(
                schema,
                FieldLocation.BODY,
                f"{path.name}#",
                _RefScope(schema, path.name, path.parent),
            )
        else:
            missing.append(f"{doc.source_id}: payloadSchemaRef {schema_ref}")
    sample: Any = None
    if sample_ref is not None:
        sample_path = _ref_path(connector, sample_ref)
        try:
            sample = (
                json.loads(sample_path.read_text(encoding="utf-8-sig")) if sample_path else None
            )
        except (OSError, json.JSONDecodeError):
            sample_path = None
        if sample_path is None:
            missing.append(f"{doc.source_id}: sampleRef {sample_ref}")
    payload = {
        "schemaRef": schema_ref,
        "schema": schema,
        "sampleRef": sample_ref,
        "sample": sample,
        "model": {"docId": model.doc_id, "title": model.title} if model is not None else None,
    }
    parts = [doc.text]
    if model is not None:
        parts.append(f"Payload: the {model.title} model (`{model.doc_id}`).")
    section = _fields_section("Payload fields", fields)
    if section:
        parts.append(section)
    return replace(
        doc,
        text="\n\n".join(parts),
        fields=tuple(fields),
        raw={**data, TRIGGER_PAYLOAD_KEY: payload},
    )


def _attach_payloads(
    documents: list[Document], connector: Path, warnings: list[str]
) -> list[Document]:
    """Trigger events' payloadSchemaRef / sampleRef, read; one warning for every ref that
    does not resolve."""
    model_ids = {d.doc_id: d for d in documents if d.kind is DocumentKind.MODEL}
    missing: list[str] = []
    out = [
        _payload_of(d, connector, model_ids, missing) if d.kind is DocumentKind.TRIGGER else d
        for d in documents
    ]
    if missing:
        shown = "; ".join(missing[:MAX_REFS_SHOWN])
        more = f"; +{len(missing) - MAX_REFS_SHOWN} more" if len(missing) > MAX_REFS_SHOWN else ""
        warnings.append(f"triggers: {len(missing)} payload ref(s) not found ({shown}{more})")
    return out


def doc_anchor(value: Any) -> str | None:
    """A page fragment, or None: an empty fragment ("#", "") is no anchor."""
    text = value.strip() if isinstance(value, str) else ""
    return text if text.lstrip("#").strip() else None


def model_key(name: str) -> str:
    """A gold ``model:<name>`` item (schema title or file stem) as a model document id."""
    return slug_doc_id(DocumentKind.MODEL, _slug(name))


def endpoint_key(endpoint_id: str, versions: tuple[str, ...]) -> str:
    """A producer endpoint id without a trailing ``-<API version>`` (one of the versions the
    package's app.json declares): a 1.2 id (``...-json-2026-10``) and the 1.1 id of the same
    endpoint (``...-json``) then match. Nothing is guessed beyond the declared versions."""
    for version in versions:
        suffix = f"-{version}"
        if version and endpoint_id.endswith(suffix):
            return endpoint_id[: -len(suffix)]
    return endpoint_id


def _apply_export(
    documents: list[Document],
    export: "knowledge_export.KnowledgeExport",
    warnings: list[str],
    versions: tuple[str, ...] = (),
) -> list[Document]:
    """Enrich endpoints with their page section and rules; add one guide per page."""
    by_source = {
        endpoint_key(d.source_id, versions): i
        for i, d in enumerate(documents)
        if d.kind is DocumentKind.ENDPOINT and d.source_id
    }
    rules_by_scope: dict[str, list[knowledge_export.Rule]] = {}
    for rule in export.rules:
        rules_by_scope.setdefault(endpoint_key(rule.scope, versions), []).append(rule)
    out = list(documents)
    used_rules: set[str] = set()
    for page in export.pages:
        for item_id, (anchor, section) in page.sections.items():
            index = by_source.get(endpoint_key(item_id, versions))
            if index is None:
                warnings.append(f"knowledge-export: {page.file} names unknown endpoint {item_id}")
                continue
            doc = out[index]
            extra = [f"## From the documentation page ({page.source_url}{anchor})", section]
            rules = rules_by_scope.get(endpoint_key(item_id, versions), [])
            if rules:
                extra.append("## Rules\n" + "\n".join(r.line() for r in rules))
                used_rules.update(r.rule_id for r in rules)
            out[index] = _with_rule_sources(
                replace(
                    doc,
                    text=doc.text + "\n\n" + "\n\n".join(extra),
                    anchor=doc.anchor or doc_anchor(anchor),
                ),
                rules,
            )
    for scope, rules in rules_by_scope.items():  # endpoint rules whose page section was not found
        index = by_source.get(scope)
        pending = [r for r in rules if r.rule_id not in used_rules]
        if index is not None and pending:
            doc = out[index]
            out[index] = _with_rule_sources(
                replace(
                    doc, text=doc.text + "\n\n## Rules\n" + "\n".join(r.line() for r in pending)
                ),
                pending,
            )
            used_rules.update(r.rule_id for r in pending)
    linked_rules = _attach_linked_rules(out, export, by_source, versions, used_rules)
    _attach_resource_rules(out, export, by_source, versions, linked_rules)
    _attach_page_rules(out, export, by_source, versions, used_rules)
    leftover = [r for r in export.rules if r.rule_id not in used_rules]
    if leftover:
        shown = "; ".join(f"{r.rule_id} {r.source_url or '(no sourceUrl)'}" for r in leftover[:3])
        more = f"; +{len(leftover) - 3} more" if len(leftover) > 3 else ""
        warnings.append(
            f"knowledge-export: {len(leftover)} rule(s) matched no endpoint or page "
            f"(e.g. {shown}{more})"
        )
    return out


def _attach_page_rules(
    out: list[Document],
    export: "knowledge_export.KnowledgeExport",
    by_source: dict[str, int],
    versions: tuple[str, ...],
    used_rules: set[str],
) -> None:
    """Rules not placed yet go to the pages they are stated on: one guide per page (appended to
    ``out``), or, for a one-endpoint page that could not be cut, into that endpoint."""
    page_of = _rule_pages(export, used_rules)
    owner: dict[str, int] = {}  # a repeated rule id belongs to the rule a page claims first
    for number, page in enumerate(export.pages):
        page_rules = []
        for n, r in enumerate(export.rules):
            if number in page_of.get(n, ()) and owner.setdefault(r.rule_id, n) == n:
                page_rules.append(r)
        indexes = [
            i
            for item_id, _ in page.items
            if (i := by_source.get(endpoint_key(item_id, versions))) is not None
        ]
        endpoints = [out[i].doc_id for i in indexes]
        if not page.split and page_rules and len(set(indexes)) == 1:
            # A one-endpoint page that could not be cut: its rules-only guide would just
            # duplicate the endpoint in search; the rules go into the endpoint instead.
            doc = out[indexes[0]]
            out[indexes[0]] = _with_rule_sources(
                replace(
                    doc,
                    text=doc.text
                    + "\n\n## Rules (documentation page)\n"
                    + "\n".join(r.line() for r in page_rules),
                ),
                page_rules,
            )
            continue
        guide = _page_guide(page, page_rules, endpoints)
        if guide is not None:
            out.append(_with_rule_sources(guide, page_rules))
    used_rules.update(owner)


def url_key(url: str) -> str:
    """A page URL compared loosely: percent-decoded (so encoded and decoded paths are equal),
    no fragment, no trailing slash, scheme and host lower case; the query is kept."""
    parts = urlsplit(unquote(url.strip()))
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


class _PageFinder:
    """A page (index into ``export.pages``) by URL: the exact URL first, then the loose key
    (``url_key``), then the URL without its query when exactly one page has that path (a page
    whose query string the rule left out; where several pages share a path, the query
    identifies the page and is required)."""

    def __init__(self, pages: "list[knowledge_export.ExportPage]") -> None:
        self._exact: dict[str, int] = {}
        self._loose: dict[str, int] = {}
        self._bare: dict[str, list[int]] = {}
        for number, page in enumerate(pages):
            self._exact.setdefault(page.source_url.rstrip("/"), number)
            key = url_key(page.source_url)
            self._loose.setdefault(key, number)
            self._bare.setdefault(key.split("?", 1)[0], []).append(number)

    def find(self, url: str) -> int | None:
        key = url_key(url)
        found = self._exact.get(url.rstrip("/"), self._loose.get(key))
        if found is None and "?" not in key:
            only = self._bare.get(key, [])
            found = only[0] if len(only) == 1 else None
        return found

    def pages_of(self, rule: "knowledge_export.Rule") -> list[int]:
        """The pages of every URL the rule names (sourceUrl first), without repeats."""
        found = (self.find(u) for u in rule.urls)
        return list(dict.fromkeys(n for n in found if n is not None))


def _rule_pages(export: "knowledge_export.KnowledgeExport", used: set[str]) -> dict[int, list[int]]:
    """Each pending rule's pages, as rule index -> page indexes (rule ids can repeat; a rule
    with ``sourceUrls`` has several pages)."""
    finder = _PageFinder(export.pages)
    out: dict[int, list[int]] = {}
    for index, rule in enumerate(export.rules):
        if rule.rule_id in used:
            continue
        pages = finder.pages_of(rule)
        if pages:
            out[index] = pages
    return out


def _rule_sources(rules: "list[knowledge_export.Rule]") -> dict[str, dict[str, Any]]:
    """The citations of rules stated on several pages: rule id -> {urls (sourceUrl first), text,
    type, line (the rule's line exactly as in the document text)}."""
    return {
        r.rule_id: {"urls": list(r.urls), "text": r.text, "type": r.type, "line": r.line()}
        for r in rules
        if r.source_urls
    }


def _with_rule_sources(doc: Document, rules: "list[knowledge_export.Rule]") -> Document:
    sources = _rule_sources(rules)
    if not sources:
        return doc
    raw = dict(doc.raw) if isinstance(doc.raw, dict) else {}
    merged = {**(raw.get(RULE_SOURCES_KEY) or {}), **sources}
    return replace(doc, raw={**raw, RULE_SOURCES_KEY: merged})


def _unit_endpoint_ids(meta: JsonObj) -> list[str]:
    """A knowledge unit's endpoints: Core's ``endpointIds`` list and/or single ``endpointId``."""
    ids = [meta.get("endpointId")]
    many = meta.get("endpointIds")
    if isinstance(many, list):
        ids.extend(many)
    return list(dict.fromkeys(i.strip() for i in ids if isinstance(i, str) and i.strip()))


CONNECTOR_BASIS = "text"  # a unit's own endpointId/endpointIds come from its text


def _merge_unit_links(
    documents: list[Document],
    links: dict[str, tuple[tuple[str, ...], str]],
    warnings: list[str],
) -> list[Document]:
    """Add ``knowledge-export/unit-links.json``'s page/slug links to the knowledge units. The
    unit's own (text) links come first and keep their basis; the export only adds endpoints."""
    if not links:
        return documents
    seen: set[str] = set()
    out = []
    for doc in documents:
        entry = links.get(doc.source_id or "") if doc.kind is DocumentKind.GUIDE else None
        if entry is None or doc.doc_id.startswith("guide:page-"):
            out.append(doc)
            continue
        seen.add(doc.source_id or "")
        ids, basis = entry
        raw = dict(doc.raw or {})
        current = [i for i in raw.get("endpointIds") or [] if isinstance(i, str)]
        bases = dict(raw.get("linkBasis") or dict.fromkeys(current, CONNECTOR_BASIS))
        for item in ids:
            if item not in bases:
                bases[item] = basis
                current.append(item)
        raw.update(endpointIds=current, linkBasis=bases)
        out.append(replace(doc, raw=raw))
    unknown = sorted(set(links) - seen)
    if unknown:
        warnings.append(
            f"knowledge-export: unit-links.json names {len(unknown)} unknown unit(s), e.g. "
            + ", ".join(unknown[:3])
        )
    return out


def _link_documents(
    documents: list[Document], warnings: list[str], versions: tuple[str, ...]
) -> list[Document]:
    """Cross links the package states, as document ids:

    - a knowledge unit's ``endpointId``/``endpointIds`` -> raw ``endpoints`` on the unit and
      raw ``x-plume-guides`` on each endpoint;
    - an endpoint's ``requiredScopes[{authId, scopes}]`` -> raw ``scopeEndpoints`` (scope ->
      endpoint ids) on the auth scheme it names (every scheme when ``authId`` is absent).

    Packages without them are unchanged."""
    by_source = {
        endpoint_key(d.source_id, versions): d.doc_id
        for d in documents
        if d.kind is DocumentKind.ENDPOINT and d.source_id
    }
    guides_of: dict[str, list[str]] = {}
    linked = [_link_unit(d, by_source, versions, guides_of, warnings) for d in documents]
    scope_endpoints = _scope_endpoints(linked)
    return [_with_links(d, guides_of, scope_endpoints) for d in linked]


def _link_unit(
    doc: Document,
    by_source: dict[str, str],
    versions: tuple[str, ...],
    guides_of: dict[str, list[str]],
    warnings: list[str],
) -> Document:
    raw = dict(doc.raw) if doc.kind is DocumentKind.GUIDE and doc.raw else {}
    ids = raw.get("endpointIds")
    if not isinstance(ids, list) or not ids:
        return doc
    found = raw.get("linkBasis")
    bases: dict[str, Any] = found if isinstance(found, dict) else {}
    basis_of: dict[str, str] = {}
    for item in ids:
        target = by_source.get(endpoint_key(item, versions))
        if target is None:
            warnings.append(f"knowledge {doc.source_id}: unknown endpoint {item}")
            continue
        basis_of.setdefault(target, str(bases.get(item) or CONNECTOR_BASIS))
        if doc.doc_id not in guides_of.setdefault(target, []):
            guides_of[target].append(doc.doc_id)
    links = [{"endpoint": t, "linkBasis": b} for t, b in basis_of.items()]
    return replace(doc, raw={**raw, "endpoints": list(basis_of), "endpointLinks": links})


def _scope_endpoints(documents: list[Document]) -> dict[str, dict[str, list[str]]]:
    """Auth scheme id -> scope -> the endpoints whose requiredScopes name it."""
    schemes = [d.source_id for d in documents if d.kind is DocumentKind.AUTH and d.source_id]
    out: dict[str, dict[str, list[str]]] = {}
    for doc in documents:
        if doc.kind is not DocumentKind.ENDPOINT or not isinstance(doc.raw, dict):
            continue
        for entry in doc.raw.get("requiredScopes") or []:
            if not isinstance(entry, dict):
                continue
            auth = _str(entry.get("authId"))
            scopes = [x for x in entry.get("scopes") or [] if isinstance(x, str)]
            for scheme in [auth] if auth else schemes:
                per = out.setdefault(scheme, {})
                for scope in scopes:
                    if doc.doc_id not in per.setdefault(scope, []):
                        per[scope].append(doc.doc_id)
    return out


def _with_links(
    doc: Document,
    guides_of: dict[str, list[str]],
    scope_endpoints: dict[str, dict[str, list[str]]],
) -> Document:
    if doc.kind is DocumentKind.ENDPOINT and doc.doc_id in guides_of:
        return replace(doc, raw={**(doc.raw or {}), "x-plume-guides": guides_of[doc.doc_id]})
    if doc.kind is DocumentKind.AUTH and doc.source_id in scope_endpoints:
        links = scope_endpoints[doc.source_id]
        return replace(doc, raw={**(doc.raw or {}), "scopeEndpoints": links})
    return doc


def _attach_linked_rules(
    out: list[Document],
    export: "knowledge_export.KnowledgeExport",
    by_source: dict[str, int],
    versions: tuple[str, ...],
    used_rules: set[str],
) -> set[str]:
    """A rule's ``endpointIds`` put it into those endpoints (before the resource fallback). An
    endpoint-scoped rule is then used; a resource rule stays in its page guide too. Returns the
    ids of the rules placed this way."""
    linked: dict[int, list[knowledge_export.Rule]] = {}
    placed: set[str] = set()
    for rule in export.rules:
        if rule.rule_id in used_rules or not rule.endpoint_ids:
            continue
        for item in rule.endpoint_ids:
            index = by_source.get(endpoint_key(item, versions))
            if index is not None:
                linked.setdefault(index, []).append(rule)
                placed.add(rule.rule_id)
    for index, rules in linked.items():
        doc = out[index]
        text = "## Rules\n" + "\n".join(dict.fromkeys(r.line() for r in rules))
        out[index] = _with_rule_sources(replace(doc, text=doc.text + "\n\n" + text), rules)
    used_rules.update(
        r.rule_id for r in export.rules if r.rule_id in placed and r.scope != "resource"
    )
    return placed


def _resource_key(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def _attach_resource_rules(
    out: list[Document],
    export: "knowledge_export.KnowledgeExport",
    by_source: dict[str, int],
    versions: tuple[str, ...],
    skip: set[str] | None = None,
) -> None:
    """A resource-scoped rule ("the Logistic Centers API requires the .../read scope") also goes
    into the text of the endpoints its page lists for that resource. The page guide keeps it too:
    the rule is about the endpoint, and a question about it should find the endpoint."""
    finder = _PageFinder(export.pages)
    placed: dict[int, list[knowledge_export.Rule]] = {}
    for rule in export.rules:
        if rule.scope != "resource" or not rule.resource or not rule.urls:
            continue
        if skip and rule.rule_id in skip:  # placed by its endpointIds
            continue
        for number in finder.pages_of(rule):  # every page the rule is stated on
            for item_id, _ in export.pages[number].items:
                index = by_source.get(endpoint_key(item_id, versions))
                if index is None:
                    continue
                if _resource_key(out[index].resource) == _resource_key(rule.resource):
                    placed.setdefault(index, []).append(rule)
    for index, rules in placed.items():
        doc = out[index]
        text = "## Rules for this resource\n" + "\n".join(dict.fromkeys(r.line() for r in rules))
        out[index] = _with_rule_sources(replace(doc, text=doc.text + "\n\n" + text), rules)


def _page_guide(
    page: "knowledge_export.ExportPage",
    rules: "list[knowledge_export.Rule]",
    endpoints: list[str] | None = None,
) -> Document | None:
    """The page's guide. A page that could not be cut into endpoint sections keeps only its
    rules and an endpoint index: its whole text would duplicate every endpoint on it and
    outrank them."""
    if page.split:
        parts = [f"# {page.title} (documentation page)", page.intro]
    elif rules:
        listing = "\n".join(f"- {label}" for _, label in page.items)
        parts = [f"# {page.title} (documentation page: rules)", f"## Endpoints\n{listing}"]
    else:
        return None
    if rules:
        parts.append("## Rules\n" + "\n".join(r.line() for r in rules))
    slug = _slug(page.source_url.rstrip("/").split("://", 1)[-1].replace("/", "-"))
    return Document(
        doc_id=slug_doc_id(DocumentKind.GUIDE, f"page-{slug}"[:200]),
        kind=DocumentKind.GUIDE,
        title=page.title,
        text="\n\n".join(p for p in parts if p),
        source_url=page.source_url or None,
        source_id=page.file,
        # the endpoints documented on this page (search keeps one next to the page)
        raw={"endpoints": list(dict.fromkeys(endpoints or ()))} if endpoints else None,
    )
