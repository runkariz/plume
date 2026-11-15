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
import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from plume.application.errors import SourcePackageError
from plume.application.ports.package_source import SourcePackage
from plume.domain.knowledge.api import ApiId, ApiInfo, Category
from plume.domain.knowledge.document import (
    Document,
    DocumentKind,
    FieldLocation,
    FieldSpec,
    endpoint_doc_id,
    normalize_endpoint_path,
    slug_doc_id,
)
from plume.domain.knowledge.model_names import display_names, parse_bundled_title
from plume.infrastructure.sources import knowledge_export

JsonObj = dict[str, Any]
MAX_FIELD_DEPTH = 6
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


def _type_of(schema: Mapping[str, Any]) -> str | None:
    t = schema.get("type")
    if isinstance(t, list):
        names = [x for x in t if isinstance(x, str) and x != "null"]
        return "|".join(names) or None
    if isinstance(t, str):
        return t
    if "$ref" in schema and isinstance(schema["$ref"], str):
        return schema["$ref"].rsplit("/", 1)[-1].removesuffix(".schema.json")
    return None


def _walk_fields(
    schema: Mapping[str, Any],
    location: FieldLocation,
    pointer: str,
    prefix: str = "",
    depth: int = 0,
) -> Iterator[FieldSpec]:
    if depth > MAX_FIELD_DEPTH:
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
                description=_str(sub.get("description")),
                pointer=sub_pointer,
            )
            yield from _walk_fields(sub, location, sub_pointer, full, depth + 1)
    items = schema.get("items")
    if isinstance(items, dict):
        yield from _walk_fields(items, location, f"{pointer}/items", f"{prefix}[]", depth + 1)


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


def _fields_section(title: str, fields: list[FieldSpec]) -> str:
    if not fields:
        return ""
    lines = [f"## {title}"]
    for f in fields:
        bits = [f"`{f.name}`"]
        if f.type:
            bits.append(f"({f.type})")
        if f.required:
            bits.append("required")
        line = " ".join(bits)
        if f.description:
            line += f": {f.description}"
        lines.append(f"- {line}")
    return "\n".join(lines)


def _obj(value: object) -> JsonObj:
    return value if isinstance(value, dict) else {}


def _url_path(url: str) -> str:
    path = _TEMPLATE_VAR.sub(r"{\1}", url)
    path = _TEMPLATE_ANY.sub("", path)
    return re.sub(r"^[a-z]+://[^/]+", "", path)


_REQUEST_SCHEMAS = (
    ("variablesContractRef", FieldLocation.PATH, "Path parameters"),
    ("paramsContractRef", FieldLocation.QUERY, "Query parameters"),
    ("headersContractRef", FieldLocation.HEADER, "Headers"),
    ("bodyContractRef", FieldLocation.BODY, "Request body"),
)


def _endpoint_fields(
    folder: Path, req: JsonObj
) -> tuple[dict[str, list[FieldSpec]], list[FieldSpec]]:
    sections: dict[str, list[FieldSpec]] = {}
    for ref_key, location, title in _REQUEST_SCHEMAS:
        ref = _str(req.get(ref_key))
        data = _opt_json(folder / ref) if ref else None
        if data is not None:
            sections[title] = list(_walk_fields(data, location, f"{ref}#"))
    response_fields: list[FieldSpec] = []
    for response in req.get("responses") or []:
        status = response.get("statusCode") if isinstance(response, dict) else None
        ref = _str(response.get("contentContractRef")) if isinstance(response, dict) else None
        if ref and isinstance(status, int) and 200 <= status < 300:
            data = _opt_json(folder / ref)
            if data is not None:
                response_fields.extend(_walk_fields(data, FieldLocation.RESPONSE, f"{ref}#"))
    return sections, response_fields


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
) -> str:
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
        parts.append(_fields_section(title, sections.get(title, [])))
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
    parts.append(_fields_section("Response fields", response_fields))
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

        documents: list[Document] = [self._app_document(info, app)]
        seen: set[str] = {documents[0].doc_id}

        def add(doc: Document, origin: str) -> None:
            if doc.doc_id in seen:
                warnings.append(f"duplicate document id {doc.doc_id} ({origin}); kept the first")
                return
            seen.add(doc.doc_id)
            documents.append(doc)

        for folder in sorted((connector / "endpoints").glob("*/")):
            request = folder / "request.json"
            if request.is_file():
                add(self._endpoint(folder, _read_json(request), versions), folder.name)
        for model in self._models(connector):
            add(model, model.doc_id)
        for doc, origin in self._guides_and_auth(connector, warnings):
            add(doc, origin)
        export = package_root / "knowledge-export"
        if export.is_dir() and knowledge_export.detect(export):
            documents = _apply_export(documents, knowledge_export.load(export), warnings)
        elif export.is_dir():
            for path in sorted(export.rglob("*.md")):
                add(self._export_page(path, export), str(path.relative_to(export)))

        manifest = _opt_json(package_root / "manifest.json") or {}
        return SourcePackage(
            api=info,
            documents=tuple(documents),
            package_hash=self._hash(connector, export if export.is_dir() else None),
            source_ref=str(package_root),
            run_id=_str(manifest.get("runId")),
            contract_version=contract_version,
            warnings=tuple(warnings),
        )

    # -- pieces --------------------------------------------------------------------------------

    @staticmethod
    def _hash(connector: Path, export: Path | None) -> str:
        digest = hashlib.sha256()
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
        return ApiInfo(
            api_id=ApiId.from_name(name),
            name=display_name(name, [summary, _str(app.get("description")) or ""]),
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
    def _endpoint(folder: Path, req: JsonObj, versions: tuple[str, ...]) -> Document:
        method = _str(req.get("method"))
        url = _str(req.get("url"))
        if method is None or url is None:
            raise SourcePackageError(f"endpoint {folder.name}: method and url are required")
        path = normalize_endpoint_path(_url_path(url), versions)
        method = method.upper()
        name = _str(req.get("name")) or f"{method} {path}"
        sections, response_fields = _endpoint_fields(folder, req)
        scopes = _required_scopes(req)
        deprecated = bool(req.get("isDeprecated")) or bool(req.get("deprecation"))
        provenance = _obj(req.get("provenance"))
        return Document(
            doc_id=endpoint_doc_id(method, path),
            kind=DocumentKind.ENDPOINT,
            title=name,
            text=_endpoint_text(
                req, name, f"{method} {path}", sections, response_fields, scopes, deprecated
            ),
            source_url=_str(provenance.get("sourceUrl")) or _str(req.get("docLink")),
            anchor=_str(provenance.get("docAnchor")),
            resource=_str(req.get("resource")),
            method=method,
            path=path,
            deprecated=deprecated,
            fields=tuple(f for fs in sections.values() for f in fs) + tuple(response_fields),
            scopes=scopes,
            source_id=_str(req.get("endpointId")),
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
            if not path.name.endswith((".variables.schema.json", ".variables.sample.json")):
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
        fields = list(_walk_fields(data, FieldLocation.MODEL, f"{path.name}#"))
        complete = data.get("x-complete") is not False
        parts = [f"# {title} (model)"]
        if _str(data.get("description")):
            parts.append(str(data["description"]))
        if not complete:
            parts.append("Note: the source marks this model as incomplete.")
        section = _fields_section("Fields", fields)
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
        return Document(
            doc_id=slug_doc_id(DocumentKind.GUIDE, _slug(key)),
            kind=DocumentKind.GUIDE,
            title=title,
            text=body.strip() or title,
            source_url=_str(meta.get("sourceUrl")),
            source_id=key,
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
        return Document(
            doc_id=slug_doc_id(DocumentKind.AUTH, _slug(key)),
            kind=DocumentKind.AUTH,
            title=title,
            text="\n\n".join(parts),
            scopes=tuple(dict.fromkeys(scopes)),
            source_id=key,
        )

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


def _renamed(model: Document, name: str) -> Document:
    """A bundler-titled model under its display name; the vendor title stays as source_id.

    A bundle root (a whole response/request body) gets no resource: it is not a concept."""
    original = model.title
    parsed = parse_bundled_title(original)
    resource = None if parsed is not None and parsed.is_root else name
    body = model.text.split("\n\n", 1)[1] if "\n\n" in model.text else ""
    text = f"# {name} (model)\n\nSource title: {original}" + (f"\n\n{body}" if body else "")
    return replace(model, title=name, resource=resource, text=text, source_id=original)


def _apply_export(
    documents: list[Document], export: "knowledge_export.KnowledgeExport", warnings: list[str]
) -> list[Document]:
    """Enrich endpoints with their page section and rules; add one guide per page."""
    by_source = {d.source_id: i for i, d in enumerate(documents) if d.kind is DocumentKind.ENDPOINT}
    rules_by_scope: dict[str, list[knowledge_export.Rule]] = {}
    for rule in export.rules:
        rules_by_scope.setdefault(rule.scope, []).append(rule)
    out = list(documents)
    used_rules: set[str] = set()
    for page in export.pages:
        for item_id, (anchor, section) in page.sections.items():
            index = by_source.get(item_id)
            if index is None:
                warnings.append(f"knowledge-export: {page.file} names unknown endpoint {item_id}")
                continue
            doc = out[index]
            extra = [f"## From the documentation page ({page.source_url}{anchor})", section]
            rules = rules_by_scope.get(item_id, [])
            if rules:
                extra.append("## Rules\n" + "\n".join(r.line() for r in rules))
                used_rules.update(r.rule_id for r in rules)
            out[index] = replace(
                doc, text=doc.text + "\n\n" + "\n\n".join(extra), anchor=doc.anchor or anchor
            )
    for scope, rules in rules_by_scope.items():  # endpoint rules whose page section was not found
        index = by_source.get(scope)
        pending = [r for r in rules if r.rule_id not in used_rules]
        if index is not None and pending:
            doc = out[index]
            out[index] = replace(
                doc, text=doc.text + "\n\n## Rules\n" + "\n".join(r.line() for r in pending)
            )
            used_rules.update(r.rule_id for r in pending)
    for page in export.pages:
        page_rules = [
            r
            for r in export.rules
            if r.rule_id not in used_rules
            and (r.source_url or "").rstrip("/") == page.source_url.rstrip("/")
        ]
        used_rules.update(r.rule_id for r in page_rules)
        parts = [f"# {page.title} (documentation page)", page.intro]
        if page_rules:
            parts.append("## Rules\n" + "\n".join(r.line() for r in page_rules))
        slug = _slug(page.source_url.rstrip("/").split("://", 1)[-1].replace("/", "-"))
        out.append(
            Document(
                doc_id=slug_doc_id(DocumentKind.GUIDE, f"page-{slug}"[:200]),
                kind=DocumentKind.GUIDE,
                title=page.title,
                text="\n\n".join(p for p in parts if p),
                source_url=page.source_url or None,
                source_id=page.file,
            )
        )
    leftover = [r for r in export.rules if r.rule_id not in used_rules]
    if leftover:
        warnings.append(f"knowledge-export: {len(leftover)} rule(s) matched no endpoint or page")
    return out
