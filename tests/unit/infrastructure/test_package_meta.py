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


def test_sources_attribution_and_conflicts_in_streams_final_shape(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    (root / "connector").mkdir(parents=True)
    spec, docs = "https://v/openapi.json", "https://v/docs/orders/"
    _write(root, "manifest.json", {
        "source": {"url": "https://v/docs"},
        "sources": [
            {"url": spec, "kind": "SPEC", "fetchedAt": "2026-11-17T00:00:00Z",
             "contentSha256": "s1", "role": "discovered from https://v/docs"},
            {"url": docs, "kind": "docs", "etag": "e1", "role": "entry"},
            {"url": "https://v/x", "kind": "weird"},
        ],
        "changelogUrls": ["https://v/changelog"],
    })  # fmt: skip
    _write(root, "pages.json", {"pages": [], "units": {
        "get-orders": {
            "sources": [{"url": spec, "kind": "spec", "fields": ["id"]},
                        {"url": docs, "kind": "docs", "fields": ["status"]}],
            "conflictsChecked": True,
            "conflicts": [{"field": "status", "values": [{"url": spec, "value": "string"},
                                                         {"url": docs, "value": "enum"}],
                           "chosen": "enum", "reason": "docs are newer"}],
        },
        "get-products": {"fieldsAttribution": "not-recorded", "conflictsChecked": False,
                         "sources": [{"url": docs}]},
    }})  # fmt: skip
    meta = read_package_meta(str(root))
    assert [(s["url"], s["kind"], s["role"]) for s in meta.sources] == [
        (spec, "spec", "discovered from https://v/docs"),
        (docs, "docs", "entry"),
        ("https://v/x", "other", None),
    ]
    assert meta.changelog_urls == ("https://v/changelog",)
    assert meta.unit_sources == {"get-orders": (spec, docs)}  # not-recorded: no attribution
    assert meta.conflicts[0]["unit"] == "get-orders"
    assert meta.conflicts[0]["chosen"] == "enum"
    assert meta.conflicts_checked == {"get-orders"}
    assert meta.conflicts_unchecked == {"get-products"}
    assert meta.source_kind(spec) == "spec"


def test_without_sources_the_manifest_source_url_is_the_one_docs_source(tmp_path: Path) -> None:
    (tmp_path / "connector").mkdir()
    _write(tmp_path, "manifest.json", {"source": {"url": "https://v/docs"}})
    meta = read_package_meta(str(tmp_path))
    assert [(s["url"], s["kind"], s["role"]) for s in meta.sources] == [
        ("https://v/docs", "docs", "entry")
    ]
