from plume.interfaces.payloads import api_ref


def test_short_name_keeps_the_casing() -> None:
    assert api_ref("woocommerce", "WooCommerce")["shortName"] == "WooCommerce"
    assert api_ref("shopify", "Shopify Admin REST API")["shortName"] == "Shopify"
    assert api_ref("acme", "acme")["shortName"] == "Acme"
    assert api_ref("x", "")["shortName"] == ""
