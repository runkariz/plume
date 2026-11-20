"""OAuth2 auth units say where their header comes from: the vendor (quoted) or the OAuth 2.0
standard (RFC 6750), which is never cited as the vendor's text."""

import json
import shutil
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.domain.knowledge.document import STANDARD_HEADER_NOTE
from plume.interfaces.http.app import HttpDependencies, create_app
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

UNIT = "oauth2-authorization-code"


def _client(packages: Path, tmp_path: Path, **header: Any) -> tuple[FakeStack, TestClient]:
    dst = tmp_path / "shopify"
    shutil.copytree(packages / "shopify-mini", dst)
    path = dst / "connector" / "auth" / f"{UNIT}.json"
    unit = json.loads(path.read_text())
    unit.update(header)
    path.write_text(json.dumps(unit))
    stack = FakeStack(embedder=WordEmbedder())
    stack.load(str(dst))
    app = create_app(
        HttpDependencies(
            overviews=stack.overviews, browse=stack.browse, search=stack.search,
            get_document=stack.get_document, find_fact=stack.find_fact,
            check_call=stack.check_call, list_builds=lambda: ListBuilds(stack.builds, stack.tags),
            diff_builds=lambda: DiffBuilds(stack.builds), resolver=stack.resolver,
            sections=stack.sections, rate_limit_per_minute=0,
        )
    )  # fmt: skip
    return stack, TestClient(app)


def test_a_standard_header_is_labelled_and_never_quoted(packages: Path, tmp_path: Path) -> None:
    stack, http = _client(packages, tmp_path, headerName="Authorization", headerPrefix="Bearer",
                          headerSource="standard:rfc6750")  # fmt: skip
    scheme = http.get(f"/v1/apis/shopify/auth/{UNIT}").json()
    assert (scheme["headerName"], scheme["headerPrefix"]) == ("Authorization", "Bearer")  # raw
    assert scheme["headerFormat"] == "Authorization: Bearer <token>"  # one space either way
    doc = stack.get_document().execute("shopify", f"auth:{UNIT}").document
    assert "Header: `Authorization: Bearer <token>`: OAuth 2.0 standard (RFC 6750)" in doc.text
    assert scheme["headerSource"] == "standard:rfc6750"
    assert scheme["headerNote"] == STANDARD_HEADER_NOTE
    assert scheme["headerEvidence"] is None
    [summary] = http.get("/v1/apis/shopify/auth").json()["schemes"]
    assert summary["headerNote"] == STANDARD_HEADER_NOTE
    fact = http.post("/v1/apis/shopify/find-fact", json={"name": "authorization"}).json()
    [match] = [m for m in fact["matches"] if m["ownerId"] == f"auth:{UNIT}"]
    assert match["note"] == STANDARD_HEADER_NOTE
    assert match["evidence"]["quote"] is None  # no vendor quote for the standard


def test_a_vendor_header_carries_its_quote(packages: Path, tmp_path: Path) -> None:
    quote = "Include the token in the X-Shopify-Access-Token header on every request."
    _, http = _client(packages, tmp_path, headerSource="vendor", headerEvidence=quote)
    scheme = http.get(f"/v1/apis/shopify/auth/{UNIT}").json()
    assert (scheme["headerSource"], scheme["headerEvidence"]) == ("vendor", quote)
    assert scheme["headerNote"] is None
    fact = http.post("/v1/apis/shopify/find-fact", json={"name": "X-Shopify-Access-Token"}).json()
    [match] = [m for m in fact["matches"] if m["ownerId"] == f"auth:{UNIT}"]
    assert (match["evidence"]["quote"], match["note"]) == (quote, None)


def test_an_unknown_source_shows_nothing(packages: Path, tmp_path: Path) -> None:
    _, http = _client(packages, tmp_path)
    scheme = http.get(f"/v1/apis/shopify/auth/{UNIT}").json()
    assert scheme["headerSource"] is None
    assert scheme["headerNote"] is None
    assert scheme["headerName"] == "X-Shopify-Access-Token"


def test_the_header_format_has_one_space_after_the_prefix() -> None:
    from plume.domain.knowledge.document import header_format  # noqa: PLC0415

    assert header_format("Authorization", "Bearer") == "Authorization: Bearer <token>"
    assert header_format("Authorization", "Bearer ") == "Authorization: Bearer <token>"
    assert header_format("X-Api-Key", None) == "X-Api-Key: <token>"


def test_the_standard_label_only_on_authorization_bearer(packages: Path, tmp_path: Path) -> None:
    """Stream's held Shopify 20a: headerName X-Shopify-Access-Token, prefix "", headerSource
    standard:rfc6750. Plume must not put the standard label on Shopify's own header: unknown
    (no label, no source, no field), and a maintainer-only package warning."""
    stack, http = _client(packages, tmp_path, headerName="X-Shopify-Access-Token",
                          headerPrefix="", headerSource="standard:rfc6750")  # fmt: skip
    scheme = http.get(f"/v1/apis/shopify/auth/{UNIT}").json()
    assert (scheme["headerSource"], scheme["headerNote"], scheme["headerFormat"]) == (
        None, None, None,
    )  # fmt: skip
    doc = stack.get_document().execute("shopify", f"auth:{UNIT}").document
    assert "RFC 6750" not in doc.text
    assert doc.fields == ()  # no header field claiming the standard
    warnings = [w.text for w in stack.sections().package_warnings("shopify")]
    assert any(w.startswith("plume-header-source-not-standard: ") for w in warnings)
    assert all(n["code"] != "plume-header-source-not-standard"
               for n in stack.sections().notices("shopify"))  # fmt: skip
