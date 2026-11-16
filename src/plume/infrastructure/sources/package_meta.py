"""What a stream package says about its own extraction, for release notes.

Read at load from the package folder (never from the connector): the manifest's stream version,
rules hash and run id; quality blockers per unit; failed knowledge-export pages; and, when stream
provides them (pages.json, changes.json), per-page hashes, source snapshots, truncation flags and
the vendor changelog. Missing files mean "no evidence", never an error.
"""

import json
from pathlib import Path
from typing import Any

from plume.domain.knowledge.release_notes import PackageMeta

MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024  # all source snapshots of one package, in memory at load


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _root(ref: str) -> Path:
    root = Path(ref).expanduser().resolve()
    if root.name == "connector" or (root / "app.json").is_file():
        return root.parent
    return root


def _entries(data: Any, key: str) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get(key), list | dict):
        value = data[key]
        return list(value.values()) if isinstance(value, dict) else value
    return []


def _url(entry: Any) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        value = entry.get("url") or entry.get("sourceUrl")
        return value if isinstance(value, str) else None
    return None


def read_package_meta(ref: str) -> PackageMeta:  # noqa: PLR0912 - one pass over optional files
    root = _root(ref)
    manifest = _json(root / "manifest.json") or {}
    blocked: set[str] = set()
    for f in _entries(_json(root / "_quality" / "report.json"), "findings"):
        blocker = isinstance(f, dict) and str(f.get("severity", "")).lower() == "blocker"
        if blocker and f.get("endpointId"):
            blocked.add(str(f["endpointId"]))
    export = _json(root / "knowledge-export" / "index.json") or {}
    failed = {u for u in (_url(p) for p in _entries(export, "failedPages")) if u}
    pages = _json(root / "pages.json")
    hashes: dict[str, str] = {}
    texts: dict[str, str] = {}
    budget = MAX_SNAPSHOT_BYTES
    for p in _entries(pages, "pages"):
        url = _url(p)
        if not url or not isinstance(p, dict):
            continue
        status = p.get("httpStatus") or p.get("status")
        if (isinstance(status, int) and status >= 400) or p.get("reason"):
            failed.add(url)
        sha = p.get("cleanSha256") or p.get("contentSha256")
        if isinstance(sha, str):
            hashes[url] = sha
        snap = p.get("snapshot")
        if isinstance(snap, str) and budget > 0:
            path = (root / snap).resolve()
            if path.is_relative_to(root) and path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                budget -= len(text)
                texts[url] = text
    units = pages.get("units") if isinstance(pages, dict) else None
    if isinstance(units, dict):
        for unit_id, u in units.items():
            if isinstance(u, dict) and (u.get("truncated") or u.get("complete") is False):
                blocked.add(str(unit_id))
    changes = _json(root / "changes.json") or {}
    named: set[str] = set()
    for c in _entries(changes, "vendorChangelog"):
        url = _url(c)
        if url:
            named.add(url)
        if isinstance(c, dict):
            named.update(str(u) for u in (c.get("units") or []) if u)
    llm: set[str] = set()
    for source in (pages, changes, manifest):
        if isinstance(source, dict):
            llm.update(str(f) for f in (source.get("llmFiles") or []) if f)
    return PackageMeta(
        stream_version=manifest.get("streamVersion"),
        rules_hash=manifest.get("rulesHash"),
        run_id=manifest.get("runId"),
        extracted_at=manifest.get("extractedAt"),
        failed_pages=frozenset(failed),
        blocked_units=frozenset(blocked),
        page_hashes=hashes,
        changed_pages=frozenset(named),
        baseline_only=isinstance(pages, dict)
        and pages.get("baselineKind") == "snapshot-after-extraction",
        llm_files=frozenset(llm),
        page_texts=texts,
    )


class StreamPackageMetaReader:
    """The PackageMetaReader port over a package folder."""

    def read(self, ref: str) -> PackageMeta:
        return read_package_meta(ref)
