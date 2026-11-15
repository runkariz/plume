from datetime import UTC, datetime

import pytest

from plume.domain.knowledge.api import ApiId
from plume.domain.knowledge.build import Build
from plume.domain.shared.hashing import content_hash

T0 = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
T1 = datetime(2026, 11, 15, 12, 5, tzinfo=UTC)


@pytest.fixture
def shopify() -> ApiId:
    return ApiId("shopify")


@pytest.fixture
def draft(shopify: ApiId) -> Build:
    return (
        Build.start(shopify, T0)
        .with_item("endpoint/get-products", content_hash("GET /products"))
        .with_item("model/product", content_hash("Product { id, title }"))
    )


@pytest.fixture
def sealed(draft: Build) -> Build:
    return draft.seal(T1)
