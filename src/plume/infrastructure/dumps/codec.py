"""Dump format ``plume-dump`` v1: gzip of JSON lines.

Line 1 is the manifest (format, version, api, build, spec, eval, counts); then one line per
document, chunk (with its vector) and fact, in id order. The gzip header carries no name or
time, so the same build always gives the same bytes.
"""

import gzip
import io
import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from plume.application.errors import ApplicationError
from plume.application.ports.dump_store import DUMP_FORMAT, DUMP_VERSION, BuildSnapshot
from plume.application.ports.eval_repo import EvalRecord
from plume.domain.eval.metrics import EvalMetrics
from plume.domain.knowledge.api import ApiId, ApiInfo, Category
from plume.domain.knowledge.build import Build, BuildSpec, BuildStatus
from plume.domain.knowledge.chunk import Chunk
from plume.domain.knowledge.citation import Citation
from plume.domain.knowledge.document import Document, DocumentKind, FieldLocation
from plume.domain.knowledge.fact import Fact, FactKind
from plume.domain.shared.hashing import ContentHash
from plume.domain.shared.ids import BuildId
from plume.infrastructure.db.repos._codec import fields_from_json, fields_to_json

MAX_LINE = 64 * 1024 * 1024


class DumpFormatError(ApplicationError, ValueError):
    code = "invalid_dump"


def _api(a: ApiInfo) -> dict[str, Any]:
    c = a.category
    return {
        "api_id": a.api_id.value,
        "name": a.name,
        "summary": a.summary,
        "doc_link": a.doc_link,
        "icon_url": a.icon_url,
        "category": (
            {
                "key": c.key,
                "reason": c.reason,
                "confidence": c.confidence,
                "bundle_version": c.bundle_version,
            }
            if c
            else None
        ),
        "versions": list(a.versions),
    }


def _api_back(d: dict[str, Any]) -> ApiInfo:
    c = d.get("category")
    return ApiInfo(
        api_id=ApiId(d["api_id"]),
        name=d["name"],
        summary=d.get("summary", ""),
        doc_link=d.get("doc_link"),
        icon_url=d.get("icon_url"),
        category=Category(c["key"], c.get("reason"), c.get("confidence"), c.get("bundle_version"))
        if c
        else None,
        versions=tuple(d.get("versions", [])),
    )


def _build(b: Build) -> dict[str, Any]:
    s = b.spec
    return {
        "build_id": b.build_id.value,
        "api_id": b.api_id.value,
        "status": b.status.value,
        "created_at": b.created_at.isoformat(),
        "sealed_at": b.sealed_at.isoformat() if b.sealed_at else None,
        "content_hash": b.content_hash.value if b.content_hash else None,
        "items": dict(sorted((k, v.value) for k, v in b.items.items())),
        "spec": (
            {
                "package_hash": s.package_hash,
                "chunker_version": s.chunker_version,
                "embed_model": s.embed_model,
                "dims": s.dims,
                "source_ref": None,
                "run_id": s.run_id,
            }
            if s
            else None
        ),
    }


def _build_back(d: dict[str, Any]) -> Build:
    s = d.get("spec")
    return Build(
        api_id=ApiId(d["api_id"]),
        build_id=BuildId(d["build_id"]),
        created_at=datetime.fromisoformat(d["created_at"]),
        status=BuildStatus(d["status"]),
        _items={k: ContentHash(v) for k, v in d["items"].items()},
        content_hash=ContentHash(d["content_hash"]) if d.get("content_hash") else None,
        sealed_at=datetime.fromisoformat(d["sealed_at"]) if d.get("sealed_at") else None,
        spec=BuildSpec(
            s["package_hash"],
            s["chunker_version"],
            s["embed_model"],
            int(s["dims"]),
            s.get("source_ref"),
            s.get("run_id"),
        )
        if s
        else None,
    )


def _eval(r: EvalRecord) -> dict[str, Any]:
    return {
        "build_id": r.build_id.value,
        "api_id": r.api_id.value,
        "gold_hash": r.gold_hash,
        "metrics": r.metrics.as_dict(),
        "passed": r.passed,
        "message": r.message,
        "baseline_build": r.baseline_build.value if r.baseline_build else None,
        "evaluated_at": r.evaluated_at.isoformat(),
        "details": list(r.details),
    }


def _eval_back(d: dict[str, Any]) -> EvalRecord:
    return EvalRecord(
        build_id=BuildId(d["build_id"]),
        api_id=ApiId(d["api_id"]),
        gold_hash=d["gold_hash"],
        metrics=EvalMetrics.from_dict(d["metrics"]),
        passed=bool(d["passed"]),
        message=d["message"],
        baseline_build=BuildId(d["baseline_build"]) if d.get("baseline_build") else None,
        evaluated_at=datetime.fromisoformat(d["evaluated_at"]),
        details=tuple(d.get("details", [])),
    )


def _doc(d: Document) -> dict[str, Any]:
    return {
        "type": "document",
        "doc_id": d.doc_id,
        "kind": d.kind.value,
        "title": d.title,
        "text": d.text,
        "source_url": d.source_url,
        "anchor": d.anchor,
        "resource": d.resource,
        "method": d.method,
        "path": d.path,
        "deprecated": d.deprecated,
        "complete": d.complete,
        "fields": json.loads(fields_to_json(d.fields)),
        "scopes": list(d.scopes),
        "source_id": d.source_id,
        "shape": d.shape,
    }


def _doc_back(d: dict[str, Any]) -> Document:
    return Document(
        doc_id=d["doc_id"],
        kind=DocumentKind(d["kind"]),
        title=d["title"],
        text=d["text"],
        source_url=d.get("source_url"),
        anchor=d.get("anchor"),
        resource=d.get("resource"),
        method=d.get("method"),
        path=d.get("path"),
        deprecated=bool(d.get("deprecated")),
        complete=bool(d.get("complete", True)),
        fields=fields_from_json(d.get("fields", [])),
        scopes=tuple(d.get("scopes", [])),
        source_id=d.get("source_id"),
        shape=d.get("shape"),
    )


def _fact(f: Fact) -> dict[str, Any]:
    e = f.evidence
    return {
        "type": "fact",
        "kind": f.kind.value,
        "owner_id": f.owner_id,
        "owner_kind": f.owner_kind.value,
        "name": f.name,
        "resource": f.resource,
        "location": f.location.value if f.location else None,
        "data_type": f.type,
        "required": f.required,
        "complete": f.complete,
        "evidence": {
            "doc_id": e.doc_id,
            "source_url": e.source_url,
            "anchor": e.anchor,
            "quote": e.quote,
        },
    }


def _fact_back(d: dict[str, Any]) -> Fact:
    e = d["evidence"]
    return Fact(
        kind=FactKind(d["kind"]),
        owner_id=d["owner_id"],
        owner_kind=DocumentKind(d["owner_kind"]),
        name=d["name"],
        evidence=Citation(e["doc_id"], e.get("source_url"), e.get("anchor"), e.get("quote")),
        resource=d.get("resource"),
        location=FieldLocation(d["location"]) if d.get("location") else None,
        type=d.get("data_type"),
        required=bool(d.get("required")),
        complete=bool(d.get("complete", True)),
    )


def _lines(s: BuildSnapshot) -> Iterator[dict[str, Any]]:
    yield {
        "type": "manifest",
        "format": DUMP_FORMAT,
        "version": DUMP_VERSION,
        "api": _api(s.api),
        "build": _build(s.build),
        "eval": _eval(s.eval) if s.eval else None,
        "counts": {
            "documents": len(s.documents),
            "chunks": len(s.chunks),
            "facts": len(s.facts),
        },
    }
    for d in sorted(s.documents, key=lambda d: d.doc_id):
        yield _doc(d)
    for c in sorted(s.chunks, key=lambda c: c.chunk_id):
        yield {
            "type": "chunk",
            "chunk_id": c.chunk_id,
            "doc_id": c.doc_id,
            "ordinal": c.ordinal,
            "heading": c.heading,
            "text": c.text,
            "embedding": list(s.vectors.get(c.chunk_id, ())),
        }
    for f in sorted(s.facts, key=lambda f: f.fact_id):
        yield _fact(f)


def encode(snapshot: BuildSnapshot) -> bytes:
    raw = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as gz:
        for line in _lines(snapshot):
            gz.write(json.dumps(line, ensure_ascii=False, separators=(",", ":")).encode())
            gz.write(b"\n")
    return raw.getvalue()


def _read_record(
    raw: bytes,
    docs: list[Document],
    chunks: list[Chunk],
    vectors: dict[str, tuple[float, ...]],
    facts: list[Fact],
) -> None:
    if len(raw) > MAX_LINE:
        raise DumpFormatError("line too long")
    rec = json.loads(raw)
    kind = rec.get("type")
    if kind == "document":
        docs.append(_doc_back(rec))
    elif kind == "chunk":
        chunk = Chunk(
            rec["chunk_id"], rec["doc_id"], int(rec["ordinal"]), rec["heading"], rec["text"]
        )
        chunks.append(chunk)
        if rec.get("embedding"):
            vectors[chunk.chunk_id] = tuple(float(x) for x in rec["embedding"])
    elif kind == "fact":
        facts.append(_fact_back(rec))
    else:
        raise DumpFormatError(f"unknown record type {kind!r}")


def decode(data: bytes) -> BuildSnapshot:
    try:
        text = gzip.decompress(data)
    except (OSError, EOFError) as exc:
        raise DumpFormatError(f"not a gzip dump: {exc}") from exc
    lines = text.split(b"\n")
    try:
        manifest = json.loads(lines[0])
    except (json.JSONDecodeError, IndexError) as exc:
        raise DumpFormatError("missing manifest") from exc
    if manifest.get("type") != "manifest" or manifest.get("format") != DUMP_FORMAT:
        raise DumpFormatError("not a plume dump")
    if manifest.get("version") != DUMP_VERSION:
        raise DumpFormatError(f"unsupported dump version {manifest.get('version')}")
    docs: list[Document] = []
    chunks: list[Chunk] = []
    vectors: dict[str, tuple[float, ...]] = {}
    facts: list[Fact] = []
    try:
        for raw in lines[1:]:
            if raw.strip():
                _read_record(raw, docs, chunks, vectors, facts)
        snapshot = BuildSnapshot(
            api=_api_back(manifest["api"]),
            build=_build_back(manifest["build"]),
            documents=tuple(docs),
            chunks=tuple(chunks),
            vectors=vectors,
            facts=tuple(facts),
            eval=_eval_back(manifest["eval"]) if manifest.get("eval") else None,
        )
    except DumpFormatError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise DumpFormatError(f"malformed dump: {exc}") from exc
    counts = manifest.get("counts", {})
    if counts != {"documents": len(docs), "chunks": len(chunks), "facts": len(facts)}:
        raise DumpFormatError("record counts do not match the manifest")
    return snapshot
