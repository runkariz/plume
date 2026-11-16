"""What a package says about its extraction: today's files and stream's pages/changes."""

import json
from pathlib import Path

from plume.infrastructure.sources.package_meta import read_package_meta


def _write(root: Path, rel: str, data: object) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data))


def test_reads_manifest_quality_failed_pages_and_stream_additions(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    (root / "connector").mkdir(parents=True)
    _write(root, "manifest.json", {"streamVersion": "1.0", "rulesHash": "abc", "runId": "r1",
                                   "extractedAt": "2026-11-16T00:00:00Z"})  # fmt: skip
    _write(root, "_quality/report.json", {"findings": [
        {"severity": "Blocker", "endpointId": "get-orders"},
        {"severity": "Warning", "endpointId": "get-products"},
    ]})  # fmt: skip
    _write(root, "knowledge-export/index.json", {"failedPages": [{"url": "https://v/x"}]})
    _write(root, "_sources/aa.txt", "Orders page text.")
    _write(root, "pages.json", {
        "baselineKind": "snapshot-after-extraction",
        "pages": [
            {"url": "https://v/orders", "contentSha256": "raw", "cleanSha256": "clean",
             "snapshot": "_sources/aa.txt", "httpStatus": 200},
            {"url": "https://v/gone", "httpStatus": 404},
            {"url": "https://v/escape", "snapshot": "../../etc/passwd"},
        ],
        "units": {"get-variants": {"truncated": True}, "get-ok": {"complete": True}},
    })  # fmt: skip
    _write(root, "changes.json", {"vendorChangelog": [{"url": "https://v/orders",
                                                       "units": ["get-orders"]}],
                                  "llmFiles": ["_rules/x.md"]})  # fmt: skip
    meta = read_package_meta(str(root / "connector"))
    assert (meta.stream_version, meta.rules_hash, meta.run_id) == ("1.0", "abc", "r1")
    assert meta.blocked_units == {"get-orders", "get-variants"}  # blocker + truncated unit
    assert meta.failed_pages == {"https://v/x", "https://v/gone"}
    assert meta.page_hashes == {"https://v/orders": "clean"}  # the cleaned text decides
    assert meta.page_texts == {"https://v/orders": "Orders page text."}  # never outside the pkg
    assert meta.changed_pages == {"https://v/orders", "get-orders"}
    assert meta.baseline_only
    assert meta.llm_files == {"_rules/x.md"}


def test_a_package_without_any_of_it_is_empty_evidence(tmp_path: Path) -> None:
    (tmp_path / "connector").mkdir()
    meta = read_package_meta(str(tmp_path))
    assert (meta.stream_version, meta.page_hashes, meta.failed_pages) == (None, {}, frozenset())
