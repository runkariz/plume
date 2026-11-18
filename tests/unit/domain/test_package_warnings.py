"""manifest.json warnings: code = text before the first ":"; known codes give notices."""

from plume.domain.knowledge.package_warnings import (
    AUTH,
    ENVIRONMENTS,
    SIGNED,
    SIGNED_WITH_AUTH,
    notices,
    parse,
)

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


def test_auth_signed_request_reads_differently_with_an_auth_scheme() -> None:
    signed = parse(["auth-signed-request: query parameters app_key, sign, timestamp"])
    alone = notices(signed, AUTH)
    assert [(n.code, n.text) for n in alone] == [
        (
            "auth-signed-request",
            "Every request must be signed (see the setup text); there is no ready auth option yet.",
        )
    ]
    with_auth = notices(signed, AUTH, has_auth=True)
    assert with_auth[0].text == (
        "Every request must also be signed (see the setup text); Kariz can't sign requests "
        "yet, so calls will fail even with this auth."
    )
    # with auth-requires-signature too: the same signing text without a scheme -> once
    both = parse(["auth-requires-signature: x", "auth-signed-request: y"])
    assert [n.code for n in notices(both, AUTH)] == ["auth-requires-signature"]


def test_any_signing_code_says_also_signed_once_when_a_scheme_exists() -> None:
    codes = ["auth-requires-signature: x", "auth-none-public-sources: y", "auth-signed-request: z"]
    for one in codes:
        found = notices(parse([one]), AUTH, has_auth=True)
        assert [n.text for n in found] == [SIGNED_WITH_AUTH], one
    together = notices(parse(codes), AUTH, has_auth=True)
    assert [(n.code, n.text) for n in together] == [("auth-requires-signature", SIGNED_WITH_AUTH)]
    assert [n.text for n in notices(parse(codes), AUTH)] == [SIGNED]  # no scheme: plain, once
