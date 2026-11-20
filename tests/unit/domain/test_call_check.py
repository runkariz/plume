ENV_TEXT = """# eBay Commerce environments and base URLs
- production: https://api.ebay.com (default)
  - api_2: https://apiz.ebay.com
  - api_3: https://apim.ebay.com/commerce/media/v1_beta
  - auth: https://auth.ebay.com"""


def test_a_server_base_path_comes_off_the_called_path() -> None:
    """eBay gates: POST /commerce/media/v1_beta/video was not documented (stored as /video)."""
    from plume.domain.knowledge.call_check import (  # noqa: PLC0415
        endpoint_server,
        server_bases,
        without_server_base,
    )

    bases = server_bases(ENV_TEXT)
    assert [(b.key, b.prefix) for b in bases] == [("api_3", "/commerce/media/v1_beta")]
    assert [
        (b.key, rest) for b, rest in without_server_base("/commerce/media/v1_beta/video", bases)
    ] == [("api_3", "/video")]
    full = "https://apim.ebay.com/commerce/media/v1_beta/video/V1?x=1"
    assert [rest for _, rest in without_server_base(full, bases)] == ["/video/V1?x=1"]
    assert without_server_base("https://api.ebay.com/commerce/media/v1_beta/video", bases) == []
    assert without_server_base("/commerce/media/v1_betax/video", bases) == []
    assert endpoint_server("{{app_env.servers.api_3}}/video") == "api_3"
    assert endpoint_server("https://api.example.com/x") is None
    # an API whose servers carry no path: nothing to take off
    assert (
        server_bases("- production: https://api.example.com (default)\n  - api: https://x.io") == []
    )
    buy = server_bases(
        "- production: https://api.ebay.com\n  - api_2: https://apix.ebay.com/buy/order/v2"
    )
    path = "/buy/order/v2/guest_checkout_session/CS1/update_quantity"
    assert [rest for _, rest in without_server_base(path, buy)] == [
        "/guest_checkout_session/CS1/update_quantity"
    ]


def _rests(path: str, text: str) -> list[tuple[str, str]]:
    from plume.domain.knowledge.call_check import server_bases, without_server_base  # noqa: PLC0415

    return [(b.label, rest) for b, rest in without_server_base(path, server_bases(text))]


TRENDYOL_EC = """# Trendyol Export Center (AutoFT) environments and base URLs
- test (sandbox): https://stageapigw.trendyol.com/integration/ecgw. Test Ortami (Stage)
- production: https://apigw.trendyol.com/integration/ecgw (default). Canli Ortam (Production)"""


def test_an_environment_base_url_stands_for_its_primary_server() -> None:
    """The tester's scan (13cc855): a base path on the primary server (`api`, not listed again
    in the guide: it is the base URL) was not taken off; only api_2 / api_3 were."""
    from plume.domain.knowledge.call_check import server_bases  # noqa: PLC0415

    prod = "production base URL: https://apigw.trendyol.com/integration/ecgw"
    stage = "test base URL: https://stageapigw.trendyol.com/integration/ecgw"
    both = [(prod, "/v3/123/packages"), (stage, "/v3/123/packages")]  # the default first
    assert _rests("/integration/ecgw/v3/123/packages", TRENDYOL_EC) == both
    full = "https://stageapigw.trendyol.com/integration/ecgw/v1/123/stocks"
    assert _rests(full, TRENDYOL_EC) == [(stage, "/v1/123/stocks")]
    assert _rests(full.replace("stageapigw", "apigw"), TRENDYOL_EC) == [(prod, "/v1/123/stocks")]
    base = server_bases(TRENDYOL_EC)[0]
    assert base.serves("api")
    assert base.serves(None)
    cdon = ("- CDON production environment (production): https://merchants-api.cdon.com/api "
            "(default). CDON\n- CDON sandbox environment for testing (sandbox): "
            "https://merchants-api.sandbox.cdon.com/api. CDON sandbox")  # fmt: skip
    assert [r for _, r in _rests("/api/v1/orders", cdon)] == ["/v1/orders", "/v1/orders"]
    sandbox = "https://merchants-api.sandbox.cdon.com/api/v1/orders?page=2"
    assert [r for _, r in _rests(sandbox, cdon)] == ["/v1/orders?page=2"]
    kaufland = "- production: https://sellerapi.kaufland.com/v2 (default). Production"
    assert [r for _, r in _rests("https://sellerapi.kaufland.com/v2/orders", kaufland)] == [
        "/orders"
    ]
    lazada = "- production: https://api.lazada.sg/rest (default).\n  - auth: https://auth.lazada.com/rest"
    assert [r for _, r in _rests("/rest/orders/get", lazada)] == ["/orders/get", "/orders/get"]
    octopia = "- production: https://api.octopia-io.net/seller/v2 (default)\n  - auth: https://auth.octopia-io.net"
    assert [r for _, r in _rests("/seller/v2/offers", octopia)] == ["/offers"]


def test_a_listed_server_is_not_served_by_the_base_url() -> None:
    """Wish: the auth server is listed with its own URL, so the base URL stands for api only."""
    from plume.domain.knowledge.call_check import server_bases  # noqa: PLC0415

    wish = ("- Production (production): https://merchant.wish.com/api/v2 (default). Standard\n"
            "  - auth: https://merchant.wish.com\n"
            "- sandbox: https://sandbox.merchant.wish.com/v2. Isolated test environment.\n"
            "  - auth: https://sandbox.merchant.wish.com")  # fmt: skip
    assert [r for _, r in _rests("/api/v2/order/create-download-job", wish)] == [
        "/order/create-download-job"
    ]
    full = "https://sandbox.merchant.wish.com/v2/order/create-download-job"
    assert [r for _, r in _rests(full, wish)] == ["/order/create-download-job"]
    base = server_bases(wish)[0]
    assert base.serves("api")
    assert not base.serves("auth")


def test_a_templated_base_segment_or_host_matches_any_value() -> None:
    """BigCommerce /stores/{{store_hash}}; Magento https://{{host}}/rest/default."""
    bc = "- production: https://api.bigcommerce.com/stores/{{app_env.vars.store_hash}} (default)."
    assert [r for _, r in _rests("/stores/abc123/v3/catalog/products", bc)] == [
        "/v3/catalog/products"
    ]
    full = "https://api.bigcommerce.com/stores/abc123/v3/catalog/products"
    assert [r for _, r in _rests(full, bc)] == ["/v3/catalog/products"]
    magento = "- production: https://{{app_env.vars.host}}/rest/default (default)"
    assert [r for _, r in _rests("https://shop.example.com/rest/default/V1/orders", magento)] == [
        "/V1/orders"
    ]
    assert [r for _, r in _rests("/rest/default/V1/orders", magento)] == ["/V1/orders"]
