"""Redaction of reported text: identifiers go, the general question stays."""

import pytest

from plume.domain.reports.redact import redact_text
from plume.domain.reports.report import REPORT_POLICY, safe_text

LEAK = (
    "Our shop ACME Handels GmbH (tenant [secret], company id 4711) has no low stock mapping. "
    "Contact [email] or [number], API key [secret], server [ip], customer number KD-004711."
)


def test_the_testers_leaks_are_redacted_and_counted() -> None:
    text, n = safe_text(LEAK, REPORT_POLICY)
    assert text is not None
    for leaked in ("ACME", "GmbH", "4711", "KD-004711"):
        assert leaked not in text
    assert "[company]" in text
    assert "company id [id]" in text
    assert "customer number [id]" in text
    assert n == 3  # markers already in the text are not counted again
    current, n = safe_text(
        "none; our own field acme_min_bestand is set by hand for warehouse WH-Hamburg-Nord",
        REPORT_POLICY,
    )
    assert current == "none; our own field acme_min_bestand is set by hand for warehouse [id]"
    assert n == 1


@pytest.mark.parametrize(
    "text",
    [
        "for warehouse stock levels the order id field is missing",
        "customer_id maps to the user; shop_name is empty",
        "dates are ISO-8601, hashes SHA-256, see RFC-3339 and UTF-8",
        "How do I list orders? The customer object has an email field",
        "the order has no shop name; which location field holds the store",
        "error code 12345678 when the seller account is suspended",
    ],
)
def test_prose_field_names_and_standards_stay(text: str) -> None:
    assert redact_text(text, REPORT_POLICY) == (text, 0)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Müller & Co. KG cannot sync", "[company] cannot sync"),
        ("Foo Bar Ltd. and Baz SAS use it", "[company] and [company] use it"),
        ("order 12 is missing in location 3", "order [id] is missing in location [id]"),
        ("merchant: M-ABC-9 is blocked", "merchant: [id] is blocked"),
        ("seller #A1B2 fails", "seller #[id] fails"),
    ],
)
def test_companies_and_cued_ids(text: str, expected: str) -> None:
    assert redact_text(text, REPORT_POLICY)[0] == expected
