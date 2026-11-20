import pytest

from plume.domain.knowledge.chunk import MAX_SCHEMA_CHUNKS, chunk_document
from plume.domain.knowledge.document import Document, DocumentKind


def _doc(kind: DocumentKind, text: str) -> Document:
    return Document(doc_id=f"{kind.value}:x", kind=kind, title="Title", text=text)


def test_endpoint_is_one_chunk() -> None:
    chunks = chunk_document(_doc(DocumentKind.ENDPOINT, "# A\n\nbody\n\n## Params\n- x"))
    assert [c.chunk_id for c in chunks] == ["endpoint:x#0"]
    assert chunks[0].embed_text.startswith("Title\n\n")


def test_guide_splits_at_headings() -> None:
    chunks = chunk_document(_doc(DocumentKind.GUIDE, "intro\n\n# One\naaa\n\n## Two\nbbb"))
    assert [c.text for c in chunks] == ["intro", "# One\naaa", "## Two\nbbb"]
    assert [c.ordinal for c in chunks] == [0, 1, 2]


def test_long_text_is_split_to_size() -> None:
    text = "\n\n".join(f"paragraph {i} " + "x" * 150 for i in range(20))
    chunks = chunk_document(_doc(DocumentKind.ENDPOINT, text), max_chars=400)
    assert len(chunks) > 1
    assert all(len(c.text) <= 400 for c in chunks)
    assert "".join(c.text for c in chunks).replace("\n", "") == text.replace("\n", "")


def test_one_huge_paragraph_is_cut() -> None:
    chunks = chunk_document(_doc(DocumentKind.MODEL, "y" * 1000), max_chars=300)
    assert [len(c.text) for c in chunks] == [300, 300, 300, 100]


def test_chunking_is_deterministic_and_hashes_differ_by_role() -> None:
    doc = _doc(DocumentKind.GUIDE, "# A\nsame")
    a, b = chunk_document(doc), chunk_document(doc)
    assert a == b
    assert a[0].embed_hash != a[0].content_hash


def test_empty_text_gives_the_title() -> None:
    assert chunk_document(_doc(DocumentKind.GUIDE, "  "))[0].text == "Title"


def test_tiny_max_chars_refused() -> None:
    with pytest.raises(ValueError, match="at least"):
        chunk_document(_doc(DocumentKind.GUIDE, "x"), max_chars=10)


def test_endpoint_and_model_chunks_are_capped_guides_are_not() -> None:
    text = "# Head\n\nsummary\n\n" + "\n\n".join(
        f"- `f{i}` (string)" + "x" * 300 for i in range(200)
    )
    for kind in (DocumentKind.ENDPOINT, DocumentKind.MODEL):
        chunks = chunk_document(_doc(kind, text), max_chars=400)
        assert len(chunks) == MAX_SCHEMA_CHUNKS, kind
        assert chunks[0].text.startswith("# Head\n\nsummary")  # the head is always embedded
    guide = chunk_document(_doc(DocumentKind.GUIDE, text), max_chars=400)
    assert len(guide) > MAX_SCHEMA_CHUNKS


def test_a_long_guide_also_splits_at_plain_text_titles() -> None:
    """Mirakl guide:context: "Shop Selection" (a title line, no '#') sat in a chunk about date
    formats and offset paging."""
    body = "# Mirakl Marketplace APIs\n\nGeneral Notes\n\n" + "Notes on compatibility. " * 80
    text = (body + "\n\nShop Selection\n\nUse the shop_id parameter to select the shop."
            "\n\nYYYY : years (four-digit)\n\nA sentence that ends with a period.\n\n"
            "Offset pagination & sort\n\nUse max and offset.")  # fmt: skip
    texts = [c.text for c in chunk_document(_doc(DocumentKind.GUIDE, text), max_chars=1000)]
    assert texts[0].startswith("# Mirakl Marketplace APIs\n\nGeneral Notes")  # heading joined
    assert any(t.startswith("Shop Selection\n\nUse the shop_id") for t in texts)
    assert any(t.startswith("Offset pagination & sort") for t in texts)
    assert not any(t.startswith("YYYY") for t in texts)  # "x : y" is no title
    for line in ("Note", 'Assuming your token is "abc"', "For more, see here"):
        other = chunk_document(_doc(DocumentKind.GUIDE, f"{body}\n\n{line}\n\nMore."), 1000)
        assert not any(c.text.startswith(line + "\n") for c in other)  # callout, quote, comma
    # a guide that fits in one chunk stays whole (Newegg's rate-limits guide)
    assert len(chunk_document(_doc(DocumentKind.GUIDE, text), max_chars=6000)) == 1
