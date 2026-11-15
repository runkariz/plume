"""Write a Plume gold set from a package's ``knowledge-export/gold-questions.json``."""

import json
from pathlib import Path

from plume.application.errors import SourcePackageError
from plume.domain.knowledge.document import DocumentKind
from plume.infrastructure.sources.gold_file import convert_stream_gold
from plume.infrastructure.sources.stream_package import StreamPackageSource, endpoint_key


def import_gold(package: str, out: str) -> tuple[int, list[str]]:
    pkg = StreamPackageSource().load(package)
    root = Path(pkg.source_ref)
    gold = root / "knowledge-export" / "gold-questions.json"
    if not gold.is_file():
        raise SourcePackageError(f"{package}: no knowledge-export/gold-questions.json")
    versions = pkg.api.versions
    ids = {
        endpoint_key(d.source_id, versions): d.doc_id
        for d in pkg.documents
        if d.kind is DocumentKind.ENDPOINT and d.source_id
    }
    data, skipped = convert_stream_gold(
        gold, pkg.api.api_id.value, ids, lambda i: endpoint_key(i, versions)
    )
    Path(out).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return len(data["questions"]), skipped  # type: ignore[arg-type]
