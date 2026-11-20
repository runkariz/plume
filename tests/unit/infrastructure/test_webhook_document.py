"""The webhook delivery mechanism is a searchable guide whose headers find_fact finds
(Shopify gate F2: X-Shopify-Hmac-SHA256 was only reachable through list_triggers)."""

import json
import shutil
from pathlib import Path

from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

HOOK = "post-admin-api-latest-webhooks-json-2026-10"
VERIFICATION = {
    "algorithm": "sha256", "encoding": "base64", "header": "X-Shopify-Hmac-SHA256",
    "headerFormat": "raw", "kind": "hmac", "secretSource": "userProvided",
    "signedPayload": "raw request body",
}  # fmt: skip


def _stack(packages: Path, tmp_path: Path) -> FakeStack:
    dst = tmp_path / "shopify"
    shutil.copytree(packages / "shopify-mini", dst)
    path = dst / "connector" / "triggers" / "webhooks" / f"{HOOK}.json"
    hook = json.loads(path.read_text())
    hook["verification"] = VERIFICATION
    hook["deliveryIdFrom"] = {"in": "header", "name": "X-Shopify-Webhook-Id"}
    path.write_text(json.dumps(hook))
    stack = FakeStack(embedder=WordEmbedder())
    stack.load(str(dst))
    return stack


def test_webhook_verification_is_searchable_and_findable(packages: Path, tmp_path: Path) -> None:
    stack = _stack(packages, tmp_path)
    doc_id = f"guide:webhook-delivery-{HOOK}"
    doc = stack.get_document().execute("shopify", doc_id).document
    assert (
        "HMAC-SHA256 over the raw request body base64-encoded in the `X-Shopify-Hmac-SHA256`"
        in (doc.text)
    )
    assert "`X-Shopify-Webhook-Id` header" in doc.text
    for name in ("X-Shopify-Hmac-SHA256", "x-shopify-hmac-sha256", "X-Shopify-Hmac-Sha256"):
        found = stack.find_fact().execute("shopify", name)
        assert [m.owner_id for m in found.matches] == [doc_id], name  # header names: any case
    hits = stack.search().execute("shopify", "how do I verify a webhook signature", mode="text")
    assert doc_id in [h.doc_id for h in hits.hits[:3]]
