"""check_call says when the matched endpoint is deprecated, in the package's words (Meta's
POST /{catalog_id}/batch: unavailable in API v27 and later); the verdict is unchanged."""

from plume.application.reader.use_cases import deprecation_text
from plume.domain.knowledge.document import Document, DocumentKind

RULE = "This endpoint is deprecated and unavailable in API version v27 and later."


def _doc(text: str, raw: object = None) -> Document:
    return Document(doc_id="endpoint:POST~/{catalog_id}/batch", kind=DocumentKind.ENDPOINT,
                    title="Batch", text=text, deprecated=True, raw=raw)  # type: ignore[arg-type]  # fmt: skip


def test_the_rule_line_is_the_reason() -> None:
    text = ("# Batch\n`POST /{catalog_id}/batch` | DEPRECATED\n\n## Request fields\n"
            "- `links[].deprecation` (string): whether the link is deprecated\n\n"
            "## Rules for this resource\n"
            "- When a version is sunset, calls move on. (effect, confidence 0.9; source: \"a "
            "deprecated version\")\n"
            f"- {RULE} (constraint, confidence 0.95; source: \"…v27 and later.\")\n")  # fmt: skip
    assert deprecation_text(_doc(text)) == RULE  # not the field line, not a quote's mention


def test_the_notice_wins_and_none_is_plain() -> None:
    assert deprecation_text(_doc("t", {"deprecation": {"message": "Use items_batch.",
                                                        "sunset": "2027-01-01"}})) == (
        "Use items_batch. 2027-01-01")  # fmt: skip
    assert deprecation_text(_doc("t", {"deprecation": {}})) is None
    assert deprecation_text(_doc("# Batch\n`POST /x` | DEPRECATED")) is None
