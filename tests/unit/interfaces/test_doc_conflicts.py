"""x-kariz-conflicts: the docs state different values for a limit; Plume shows every statement
with its place (examples marked) and never picks one (OTTO GET /v4/orders: 128 vs 256)."""

import json
import shutil
from pathlib import Path

from plume.domain.knowledge.document import conflicts_of
from plume.interfaces import payloads
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

PRODUCTS = "get-admin-api-latest-products-json"
CONFLICTS = [{
    "limit": "the page size",
    "statements": [
        {"where": "description", "quote": "Results are limited to 128 per page."},
        {"where": "param:limit", "quote": "The maximum value is 250."},
        {"where": "page:https://x/guide", "quote": "e.g. limit=50", "isExample": True},
    ],
}]  # fmt: skip


def _stack(packages: Path, tmp_path: Path) -> FakeStack:
    dst = tmp_path / "shopify"
    shutil.copytree(packages / "shopify-mini", dst)
    req = dst / "connector" / "endpoints" / PRODUCTS / "request.json"
    req.write_text(json.dumps({**json.loads(req.read_text()), "x-kariz-conflicts": CONFLICTS}))
    knowledge = dst / "connector" / "knowledge"
    (knowledge / "paging.json").write_text(json.dumps(
        {"id": "paging", "title": "Paging", "x-kariz-conflicts": CONFLICTS}))  # fmt: skip
    (knowledge / "paging.md").write_text("# Paging\n\nPages of products.\n")
    stack = FakeStack(embedder=WordEmbedder())
    stack.load(str(dst))
    return stack


def test_conflicts_are_shown_with_every_statement(packages: Path, tmp_path: Path) -> None:
    stack = _stack(packages, tmp_path)
    endpoint = "endpoint:GET~/admin/api/{version}/products.json"
    for doc_id in (endpoint, "guide:paging"):
        doc = stack.get_document().execute("shopify", doc_id)
        [c] = payloads.document_payload(doc)["conflicts"]
        assert c["text"] == (
            "The docs state different values for the page size:\n"
            '- description: "Results are limited to 128 per page."\n'
            '- param:limit: "The maximum value is 250."\n'
            '- page:https://x/guide (example): "e.g. limit=50"'
        )
        assert [st["is_example"] for st in c["statements"]] == [False, False, True]
    found = stack.find_fact().execute("shopify", "limit", owner=endpoint)
    [m] = [x for x in found.matches if x.owner_id == endpoint]
    assert m.note is not None
    assert m.note.startswith("The docs state different values for the page size:")
    # check_call quotes the vendor's text as before: the parameter is documented, no pick
    call = stack.check_call().execute("shopify", "GET", "/admin/api/2026-10/products.json",
                                      ["limit"])  # fmt: skip
    assert call.params[0].found
    note = call.params[0].note or ""  # where a developer hits it (OTTO GET /v4/orders [limit])
    assert note.startswith("The docs state different values for the page size:")
    other = stack.check_call().execute("shopify", "GET", "/admin/api/2026-10/products.json",
                                       ["fields"])  # fmt: skip
    assert other.params[0].note is None


def test_malformed_conflicts_are_skipped() -> None:
    raw = {"x-kariz-conflicts": [
        {"limit": "x", "statements": [{"where": "description", "quote": "only one"}]},
        {"statements": [{"quote": "a"}, {"quote": "b"}]},
        "nonsense",
    ]}  # fmt: skip
    assert conflicts_of(raw) == ()
