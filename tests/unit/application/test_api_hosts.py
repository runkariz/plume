"""An API's own URL hosts, from its documents (templates included)."""

from pathlib import Path

from plume.application.reports.hosts import ApiHosts
from tests.fakes.stack import FakeStack


def test_hosts_named_by_the_docs_and_their_templates(packages: Path) -> None:
    stack = FakeStack()
    stack.load(str(packages / "shopify-mini"))
    known = ApiHosts(stack.resolver(), stack.documents).of("shopify")
    assert known("shopify.dev") == "shopify.dev"
    assert known("www.shopify.dev") == "shopify.dev"
    assert known("acme-gmbh.myshopify.com") == "{shop}.myshopify.com"  # the shop's name goes
    assert known("erp.nordlicht-elektro.example") is None
    assert ApiHosts(stack.resolver(), stack.documents).of("no-such-api")("shopify.dev") is None
