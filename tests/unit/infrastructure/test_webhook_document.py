# ruff: noqa: E501
"""The webhook delivery mechanism is a searchable guide whose headers find_fact finds
(Shopify gate F2: X-Shopify-Hmac-SHA256 was only reachable through list_triggers)."""

import json
import shutil
from pathlib import Path
from typing import Any

from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

HOOK = "post-admin-api-latest-webhooks-json-2026-10"
VERIFICATION = {
    "algorithm": "sha256", "encoding": "base64", "header": "X-Shopify-Hmac-SHA256",
    "headerFormat": "raw", "kind": "hmac", "secretSource": "userProvided",
    "signedPayload": "{body}",
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
    assert "HMAC-SHA256 base64-encoded in the `X-Shopify-Hmac-SHA256` header" in doc.text
    assert "The signed string is `{body}`, where {body} is the raw request body." in doc.text
    assert "The key is a secret you set." in doc.text
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


def _hook_with(packages: Path, tmp_path: Path, verification: dict[str, Any]) -> FakeStack:
    dst = tmp_path / "shopify"
    shutil.copytree(packages / "shopify-mini", dst)
    path = dst / "connector" / "triggers" / "webhooks" / f"{HOOK}.json"
    hook = json.loads(path.read_text())
    hook["verification"] = verification
    path.write_text(json.dumps(hook))
    stack = FakeStack(embedder=WordEmbedder())
    stack.load(str(dst))
    return stack


def test_a_timestamped_template_names_both_placeholders(packages: Path, tmp_path: Path) -> None:
    stack = _hook_with(packages, tmp_path, {
        "kind": "hmac", "algorithm": "sha256", "encoding": "hex", "header": "X-Signature",
        "signedPayload": "{timestamp}.{body}", "secretSource": "subscribeResponse",
    })  # fmt: skip
    doc = stack.get_document().execute("shopify", f"guide:webhook-delivery-{HOOK}").document
    assert (
        "The signed string is `{timestamp}.{body}`, where {body} is the raw request body and "
        "{timestamp} is the delivery timestamp." in doc.text
    )
    assert "The key is the secret returned when you subscribe." in doc.text
    assert "over the" not in doc.text


def test_an_unknown_secret_source_is_not_shown_but_warned(packages: Path, tmp_path: Path) -> None:
    stack = _hook_with(packages, tmp_path, {
        "kind": "hmac", "algorithm": "sha256", "header": "X-Signature",
        "signedPayload": "v0:{timestamp}", "secretSource": "the merchant's API key",
    })  # fmt: skip
    doc = stack.get_document().execute("shopify", f"guide:webhook-delivery-{HOOK}").document
    assert "The key is" not in doc.text
    assert "the merchant's API key" not in doc.text
    assert "where {timestamp} is the delivery timestamp." in doc.text  # only what is present
    build = stack.resolver().resolve("shopify").build.build_id
    app = next(d for d in stack.documents.list_documents(build) if d.kind.value == "app")
    warnings = (app.raw or {})["package_warnings"]
    assert any(w.startswith("plume-secret-source-unknown: webhook ") for w in warnings)


def test_a_free_text_signed_payload_is_not_shown_but_warned(packages: Path, tmp_path: Path) -> None:
    """Older packages wrote "body" / "raw request body": as Core's template that would sign
    those literal words, so Plume does not render it and warns the maintainers."""
    stack = _hook_with(packages, tmp_path, {
        "kind": "hmac", "algorithm": "sha256", "encoding": "base64", "header": "X-Shopify-Hmac-SHA256",
        "signedPayload": "raw request body", "secretSource": "userProvided",
    })  # fmt: skip
    doc = stack.get_document().execute("shopify", f"guide:webhook-delivery-{HOOK}").document
    assert "signed string" not in doc.text
    assert "raw request body" not in doc.text.split("## From the docs")[0]
    assert "HMAC-SHA256 base64-encoded in the `X-Shopify-Hmac-SHA256` header" in doc.text
    build = stack.resolver().resolve("shopify").build.build_id
    app = next(d for d in stack.documents.list_documents(build) if d.kind.value == "app")
    assert any(w.startswith("plume-signed-payload-not-template: webhook ")
               for w in (app.raw or {})["package_warnings"])  # fmt: skip


def test_body_null_or_empty_sign_the_raw_body(packages: Path, tmp_path: Path) -> None:
    """Core: a missing / null / empty signedPayload, or exactly "body", is the raw request body
    bytes (valid; no warning)."""
    base: dict[str, Any] = {"kind": "hmac", "algorithm": "sha256", "header": "X-Signature",
            "secretSource": "userProvided"}  # fmt: skip
    extras: list[dict[str, Any]] = [{"signedPayload": "body"}, {"signedPayload": None}, {},
              {"signedPayload": ""}]  # fmt: skip
    for i, extra in enumerate(extras):
        stack = _hook_with(packages, tmp_path / str(i), {**base, **extra})
        doc = stack.get_document().execute("shopify", f"guide:webhook-delivery-{HOOK}").document
        assert "The signed string is the raw request body." in doc.text, extra
        build = stack.resolver().resolve("shopify").build.build_id
        app = next(d for d in stack.documents.list_documents(build) if d.kind.value == "app")
        assert not any("signed-payload" in w for w in (app.raw or {}).get("package_warnings") or [])


def test_a_mechanism_is_named_by_its_evidence_spec() -> None:
    """Sendcloud's mechanisms are "portal" and "portal-2"; the event-subscriptions one is named
    by its spec's path, so "verify an event subscription webhook" finds it (it states no
    signature). Generic segments (webhooks, a version, a dot folder) name nothing."""
    from plume.infrastructure.sources.stream_package import (  # noqa: PLC0415
        _spec_label,
        _webhook_document,
    )

    url = "https://sendcloud.dev/.openapi/v3/event-subscriptions/openapi.yaml"
    assert _spec_label(url) == "event subscriptions"
    assert _spec_label("https://sendcloud.dev/.openapi/v3/webhooks/openapi.yaml") is None
    assert _spec_label("https://example.com/event-subscriptions.yaml") is None
    assert _spec_label(None) is None
    hook = {"id": "portal", "mode": "portal", "provenance": {"evidenceUrl": url}}
    doc = _webhook_document("Sendcloud", hook, several=True)
    assert doc is not None
    assert (
        doc.title == "Sendcloud webhooks (event subscriptions, portal): delivery and verification"
    )
    assert doc.doc_id == "guide:webhook-delivery-portal"  # the id does not change
    alone = _webhook_document("Sendcloud", hook)
    assert alone is not None
    assert alone.title == "Sendcloud webhooks: delivery and verification"
