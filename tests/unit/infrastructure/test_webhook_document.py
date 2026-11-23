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


def test_environments_are_a_searchable_guide_with_their_urls(packages: Path) -> None:
    stack = FakeStack(embedder=WordEmbedder())
    stack.load(str(packages / "woo-mini"))
    doc = stack.get_document().execute("woocommerce", "guide:environments-and-base-urls").document
    assert "- production: https://{host} (default)" in doc.text


def test_every_mechanism_gets_a_guide_with_its_events_and_conflicts(
    packages: Path, tmp_path: Path
) -> None:
    """Sendcloud: webhooks (HMAC) and event subscriptions (no signature stated) are two
    mechanisms; each gets its own guide, named, the second saying the package states no
    verification, with its events and the package's conflicts."""
    dst = tmp_path / "shopify"
    shutil.copytree(packages / "shopify-mini", dst)
    hooks = dst / "connector" / "triggers" / "webhooks"
    signed = json.loads((hooks / f"{HOOK}.json").read_text())
    signed["verification"] = VERIFICATION
    (hooks / f"{HOOK}.json").write_text(json.dumps(signed))
    conflict = {"text": "The docs page says deliveries are signed; the spec states no signature.",
                "statements": [{"where": "endpoint", "says": "signed"}]}  # fmt: skip
    (hooks / "portal.json").write_text(json.dumps({
        "id": "portal", "mode": "portal", "handshake": {"kind": "none"},
        "eventsAvailable": ["parcels.event.created", "parcel.created"],
        "provenance": {"evidenceUrl": "https://example.com/event-subscriptions.yaml"},
        "x-kariz-conflicts": [conflict],
    }))  # fmt: skip
    stack = FakeStack(embedder=WordEmbedder())
    stack.load(str(dst))
    get = stack.get_document()
    plain = get.execute("shopify", "guide:webhook-delivery-portal").document
    assert plain.title.endswith("webhooks (portal): delivery and verification")
    assert "The package states no signature verification for this mechanism." in plain.text
    assert "- parcels.event.created" in plain.text
    assert "- parcel.created" in plain.text
    assert plain.source_url == "https://example.com/event-subscriptions.yaml"
    assert (plain.raw or {})["x-kariz-conflicts"] == [conflict]
    hmac = get.execute("shopify", f"guide:webhook-delivery-{HOOK}").document
    assert f"({HOOK}" in hmac.title
    assert "no signature verification" not in hmac.text
    assert "x-kariz-conflicts" not in (hmac.raw or {})
    hits = stack.search().execute("shopify", "verify parcel created event deliveries")
    assert "guide:webhook-delivery-portal" in [h.doc_id for h in hits.hits[:3]]  # it is found


def test_a_bare_mechanism_still_gets_a_guide(packages: Path, tmp_path: Path) -> None:
    """Only an id: before, no document at all."""
    dst = tmp_path / "shopify"
    shutil.copytree(packages / "shopify-mini", dst)
    path = dst / "connector" / "triggers" / "webhooks" / f"{HOOK}.json"
    path.write_text(json.dumps({"id": HOOK}))
    stack = FakeStack(embedder=WordEmbedder())
    stack.load(str(dst))
    doc = stack.get_document().execute("shopify", f"guide:webhook-delivery-{HOOK}").document
    assert doc.title == "Shopify webhooks: delivery and verification"  # one mechanism: no name
    assert "The package states no signature verification for this mechanism." in doc.text
