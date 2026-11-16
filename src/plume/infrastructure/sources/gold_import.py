"""Write a Plume gold set from a package's ``knowledge-export/gold-questions.json``."""

import json
from collections import Counter
from pathlib import Path

from plume.application.errors import SourcePackageError
from plume.domain.eval.gold import GOLD_SOURCES
from plume.domain.knowledge.document import DocumentKind
from plume.infrastructure.sources.gold_file import convert_stream_gold
from plume.infrastructure.sources.stream_package import (
    StreamPackageSource,
    endpoint_key,
    model_key,
)

# Written questions per source (docs, spec), skipped question ids, index.json goldCounts.
GoldImport = tuple[dict[str, int], list[str], dict[str, int] | None]


def _item_key(item: str, versions: tuple[str, ...]) -> str:
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
    ids: dict[str, str] = {}
    for d in pkg.documents:
        if d.kind is DocumentKind.ENDPOINT and d.source_id:
            ids[endpoint_key(d.source_id, versions)] = d.doc_id
        elif d.kind is DocumentKind.MODEL:
            ids[d.doc_id] = d.doc_id  # model:<slug of the file stem>
            if d.source_id:
                ids.setdefault(model_key(d.source_id), d.doc_id)  # model:<slug of the title>
    data, skipped = convert_stream_gold(
        gold, pkg.api.api_id.value, ids, lambda i: _item_key(i, versions)
    )
    Path(out).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    written = Counter(str(q["source"]) for q in data["questions"])  # type: ignore[attr-defined]
    counts = {s: written[s] for s in GOLD_SOURCES if written[s]}
    return counts, skipped, _declared_counts(root / "knowledge-export" / "index.json")


def _declared_counts(index: Path) -> dict[str, int] | None:
    try:
        raw = json.loads(index.read_text(encoding="utf-8")).get("goldCounts")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(raw, dict):
        return None
    return {str(k): int(v) for k, v in raw.items() if isinstance(v, int)}
