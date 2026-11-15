from plume.domain.knowledge.model_names import display_names, humanize, parse_bundled_title


def test_parse() -> None:
    t = parse_bundled_title("A01_Response_200_DefaultBillingInformation_CorporateInformation")
    assert t is not None
    assert (t.operation, t.kind, t.status) == ("A01", "response", "200")
    assert t.path == ("DefaultBillingInformation", "CorporateInformation")
    root = parse_bundled_title("OR11_Response_200")
    assert root is not None
    assert root.is_root
    req = parse_bundled_title("A02_Request_Address")
    assert req is not None
    assert (req.kind, req.status, req.path) == ("request", None, ("Address",))
    assert parse_bundled_title("Customer") is None
    assert parse_bundled_title("Order response") is None


def test_humanize() -> None:
    assert humanize("CorporateInformation") == "Corporate Information"
    assert humanize("ShippingTo") == "Shipping To"
    assert humanize("VATNumber") == "VAT Number"


def test_display_names() -> None:
    names = display_names(
        [
            ("a", "A01_Response_200_BillingInfo", "s1"),
            ("b", "A01_Response_200", "s2"),
            ("c", "A02_Request_Address", "s3"),
            ("d", "DR12_Response_200_Data_ShippingTo_Address", "s4"),  # Address: 2 shapes
            ("e", "X1_Response_200_Items_Price", "p"),
            ("f", "X2_Response_200_Lines_Price", "p"),  # Price: same shape twice
            ("g", "Customer", "s9"),  # not a bundler title
        ]
    )
    assert names == {
        "a": "Billing Info",
        "b": "A01 response 200",
        "c": "Address",  # ambiguous but no parent segment
        "d": "Shipping To / Address",
        "e": "Price",
        "f": "Price",
    }
