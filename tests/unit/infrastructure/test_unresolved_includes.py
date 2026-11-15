"""Include tags left in a package (Markdoc {% partial %}, Liquid, Hugo, MDX) are flagged."""

import shutil
from pathlib import Path

import pytest

from plume.infrastructure.sources.stream_package import (
    _UNRESOLVED_INCLUDE,
    StreamPackageSource,
)


@pytest.mark.parametrize(
    "text",
    [
        '{% partial file="/partial-content/a.md" /%}',
        "{% include snippets/auth.md %}",
        "{{< include file=x.md >}}",
        '<Snippet file="auth.mdx" />',
    ],
)
def test_include_tags_are_recognised(text: str) -> None:
    assert _UNRESOLVED_INCLUDE.search(f"Intro\n\n{text}\n\nMore")


def test_plain_text_is_not_flagged() -> None:
    assert not _UNRESOLVED_INCLUDE.search("Use {id} in the path; 50% of {{ value }} is fine.")


def test_unresolved_include_marks_the_document(packages: Path, tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    shutil.copytree(packages / "test-catalog", pkg)
    knowledge = pkg / "connector" / "knowledge"
    md = next(knowledge.glob("*.md"))
    md.write_text(md.read_text() + '\n{% partial file="/partial-content/x.md" /%}\n')
    loaded = StreamPackageSource().load(str(pkg))
    flagged = [d for d in loaded.documents if not d.complete and "unresolved include" in d.text]
    assert len(flagged) == 1
    assert flagged[0].text.startswith("> Plume: this page contains 1 unresolved include tag(s)")
    assert any("unresolved include" in w for w in loaded.warnings)
    clean = StreamPackageSource().load(str(packages / "test-catalog"))
    assert not any("unresolved include" in w for w in clean.warnings)
