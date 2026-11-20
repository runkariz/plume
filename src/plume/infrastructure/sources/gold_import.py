"""Write a Plume gold set from a package's ``knowledge-export/gold-questions.json``."""

import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from plume.application.errors import SourcePackageError
from plume.domain.eval.gold import source_order
from plume.domain.knowledge.document import Document, DocumentKind
from plume.infrastructure.sources.gold_file import convert_stream_gold
from plume.infrastructure.sources.stream_package import (
    StreamPackageSource,
    endpoint_key,
    model_key,
)

# Written questions per source (docs, spec), skipped question ids, index.json goldCounts,
# expected item ids that resolve to no document (dropped from their question, reported).
GoldImport = tuple[dict[str, int], list[str], dict[str, int] | None, list[str]]
KNOWLEDGE = "knowledge:"


def _item_key(item: str, versions: tuple[str, ...]) -> str:
    if item.startswith(KNOWLEDGE):
        return item  # resolved through the unit's source id, never by rewriting the string
    if item.startswith("model:"):
        return model_key(item.removeprefix("model:"))
    return endpoint_key(item, versions)


def import_gold(package: str, out: str) -> GoldImport:
    pkg = StreamPackageSource().load(package)
    root = Path(pkg.source_ref)
    gold = root / "knowledge-export" / "gold-questions.json"
    if not gold.is_file():
        raise SourcePackageError(f"{package}: no knowledge-export/gold-questions.json")
    versions = pkg.api.versions
    units = _knowledge_unit_docs(root, pkg.documents)
    ids: dict[str, str] = {}
    for d in pkg.documents:
        if d.kind is DocumentKind.ENDPOINT and d.source_id:
            ids[endpoint_key(d.source_id, versions)] = d.doc_id
        elif d.kind is DocumentKind.MODEL:
            ids[d.doc_id] = d.doc_id  # model:<slug of the file stem>
            if d.source_id:
                ids.setdefault(model_key(d.source_id), d.doc_id)  # model:<slug of the title>
        elif d.kind is DocumentKind.GUIDE and d.source_id and d.doc_id in units:
            ids[KNOWLEDGE + d.source_id] = d.doc_id  # knowledge:<unit id> -> its guide
    data, skipped, unresolved = convert_stream_gold(
        gold, pkg.api.api_id.value, ids, lambda i: _item_key(i, versions)
    )
    Path(out).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    written = Counter(str(q["source"]) for q in data["questions"])  # type: ignore[attr-defined]
    counts = {s: written[s] for s in source_order(written) if written[s]}
    return counts, skipped, _declared_counts(root / "knowledge-export" / "index.json"), unresolved


def _knowledge_unit_docs(root: Path, documents: Sequence[Document]) -> set[str]:
    """The guides the loader made from connector/knowledge units (their source id is the unit
    id), as document ids."""
    folder = root / "connector" / "knowledge"
    unit_ids = {p.stem for p in folder.glob("*.json")} if folder.is_dir() else set()
    return {d.doc_id for d in documents if d.kind is DocumentKind.GUIDE and d.source_id in unit_ids}


def _declared_counts(index: Path) -> dict[str, int] | None:
    try:
        raw = json.loads(index.read_text(encoding="utf-8")).get("goldCounts")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(raw, dict):
        return None
    return {str(k): int(v) for k, v in raw.items() if isinstance(v, int)}
