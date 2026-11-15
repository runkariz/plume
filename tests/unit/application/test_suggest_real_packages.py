"""Concept suggestions on the real Shopify / WooCommerce / Mirakl packages.

Runs when PLUME_SUGGEST_PACKAGES lists the three package folders (colon-separated, in that
order), e.g. the 1.2 renders; skipped otherwise (the packages are not in the repository).
"""

import os

import pytest

from plume.application.models.concepts import SuggestFilter
from tests.fakes.stack import FakeStack

PATHS = [p for p in os.environ.get("PLUME_SUGGEST_PACKAGES", "").split(":") if p]
pytestmark = pytest.mark.skipif(
    len(PATHS) != 3, reason="set PLUME_SUGGEST_PACKAGES=<shopify>:<woocommerce>:<mirakl>"
)
APIS = ["shopify", "woocommerce", "mirakl"]


@pytest.fixture(scope="module")
def stack() -> FakeStack:
    s = FakeStack()
    for path in PATHS:
        s.load(path)
    return s


def test_noise_is_gone_and_core_concepts_remain(stack: FakeStack) -> None:
    result = stack.suggest().execute(APIS, SuggestFilter(only="all", limit=100))
    names: set[str] = set()
    offset: int | None = 0
    while offset is not None:
        page = stack.suggest().execute(APIS, SuggestFilter(only="all", limit=100, offset=offset))
        names.update(c.name for c in page.concepts)
        offset = page.next_offset
    assert len(names) == result.total
    assert {"Updated", "Attributes", "Entities", "Date", "Page", "Value"}.isdisjoint(names)
    assert {"Order", "Customer", "Product"} <= names
    assert "Taxes" not in names  # one concept per singular name
    top = [c.name for c in result.concepts[:3]]
    assert top == ["Order", "Customer", "Product"]


def test_no_cap_and_single_api_concepts_are_browsable(stack: FakeStack) -> None:
    multi = stack.suggest().execute(APIS, SuggestFilter(limit=100))
    assert multi.total > 24  # the old hard cap is gone
    single = stack.suggest().execute(APIS, SuggestFilter(only="single", limit=5))
    assert single.total == multi.counts.single > 100
    assert single.next_offset == 5


def test_reason_matches_counts(stack: FakeStack) -> None:
    order = stack.suggest().execute(APIS).concepts[0]
    for api, label in (("shopify", "Shopify"), ("woocommerce", "WooCommerce")):
        n = order.api_counts[api]
        assert f"{label} has an Order model and {n.endpoints} order endpoints" in order.reason
    assert order.reason.endswith("Straightforward because every API documents Order directly.")
