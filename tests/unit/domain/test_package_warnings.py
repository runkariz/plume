"""manifest.json warnings: code = text before the first ":"; known codes give notices."""

from plume.domain.knowledge.package_warnings import AUTH, ENVIRONMENTS, notices, parse

RAW = [
    'auth-requires-signature: api-key-shop-client-key "All requests must contain ..."',
    "auth-none-public-sources: requests are signed (HMAC-SHA256); no signed auth kind yet",
    "default-environment-by-order: prod-ap",
    "knowledge-links: 11 units with endpointId",
    "no colon here",
    "",
    42,
]


def test_parse_takes_the_code_before_the_first_colon() -> None:
    found = parse(RAW)
    assert [w.code for w in found] == [
        "auth-requires-signature",
        "auth-none-public-sources",
        "default-environment-by-order",
        "knowledge-links",
        "no colon here",
    ]
    assert found[3].text == "knowledge-links: 11 units with endpointId"
    assert parse(None) == []
    assert parse({"warnings": []}) == []


def test_known_codes_give_one_notice_per_section() -> None:
    found = notices(parse(RAW))
    assert [(n.code, n.section) for n in found] == [
        ("auth-requires-signature", AUTH),  # auth-none-public-sources says the same: once
        ("default-environment-by-order", ENVIRONMENTS),
    ]
    assert found[0].text.startswith("Every request must be signed")
    assert found[1].text.endswith("Choose your region.")
    assert [n.section for n in notices(parse(RAW), ENVIRONMENTS)] == [ENVIRONMENTS]


def test_auth_none_public_sources_alone_is_an_auth_notice() -> None:
    found = notices(parse(["auth-none-public-sources: signed"]), AUTH)
    assert [n.code for n in found] == ["auth-none-public-sources"]


def test_unknown_codes_give_no_notice() -> None:
    assert notices(parse(["knowledge-links: 3", "robots-disallowed: x"])) == []


def test_auth_needs_core_change_is_an_auth_notice_once() -> None:
    found = notices(
        parse(
            [
                "auth-needs-core-change: token field is access_token_value",
                "auth-needs-core-change: token sent without Bearer",
                "auth-requires-signature: x",
            ]
        ),
        AUTH,
    )
    assert [n.code for n in found] == ["auth-needs-core-change", "auth-requires-signature"]
    assert found[0].text.startswith("This API's auth uses a variant the connector can't")
    assert found[0].text.endswith("until Kariz supports it (see the setup text).")
