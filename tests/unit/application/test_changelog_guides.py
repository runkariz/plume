"""what_changed points to the vendor's own changelog guides next to Plume's build diff."""

from types import SimpleNamespace

from plume.application.reader.sections import PackageSections
from plume.domain.knowledge.document import Document, DocumentKind

GUIDES = {
    "guide:changelog": "Changelog",
    "guide:release-notes-2026": "Release notes 2026",
    "guide:whats-new": "What's new in the Admin API",
    "guide:authentication": "Authentication",
}


def test_changelog_guides_by_title_or_id() -> None:
    docs = {
        d: Document(doc_id=d, kind=DocumentKind.GUIDE, title=t, text=t) for d, t in GUIDES.items()
    }
    resolved = SimpleNamespace(build=SimpleNamespace(build_id="b"))
    sections = PackageSections(
        SimpleNamespace(resolve=lambda _a, _v=None: resolved),  # type: ignore[arg-type]
        SimpleNamespace(browse=lambda *_a, **_k: ([SimpleNamespace(doc_id=d) for d in docs], 4)),
        SimpleNamespace(get_document=lambda _b, d: docs[d]),
        SimpleNamespace(),
    )
    found = sections.changelog_guides("x")
    assert [g["doc_id"] for g in found] == [
        "guide:changelog", "guide:release-notes-2026", "guide:whats-new",
    ]  # fmt: skip
