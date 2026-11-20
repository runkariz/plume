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
