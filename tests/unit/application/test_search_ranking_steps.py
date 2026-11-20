"""Ranking steps after fusion: request-body models and near-duplicate guides give way."""

from plume.application.reader.ranking import near_duplicate_guides_last, request_models_last


def test_request_models_move_behind_the_other_results() -> None:
    """Mirakl "confirm an order has been shipped": st23-request-shipments above the endpoint."""
    ranked = ["model:st23-request-shipments", "endpoint:PUT~/api/orders/{order_id}/ship",
              "model:or11-response-200", "guide:x"]  # fmt: skip
    assert request_models_last(ranked, 5) == [
        "endpoint:PUT~/api/orders/{order_id}/ship", "model:or11-response-200", "guide:x",
        "model:st23-request-shipments",
    ]  # fmt: skip


def test_a_guide_saying_what_a_better_one_says_moves_out_of_the_top() -> None:
    """Walmart: the access token lifecycle in several near-identical sections."""
    a = "guide:lifecycle-state-machine-authentication-onboarding-troubleshooting-access-token-expiration-and-refresh-life"  # noqa: E501
    b = "guide:lifecycle-state-machine-oauth-20-authorization-access-token-expiration-and-refresh-life"  # noqa: E501
    other = "guide:validation-docs-oauth-2-0-access-token-lifecycle-and-aut"
    ranked = [a, b, other, "endpoint:POST~/token"] + [
        f"guide:topic{i}-subject{i}" for i in range(10)
    ]
    out = near_duplicate_guides_last(ranked, 5)
    assert out[:3] == [a, other, "endpoint:POST~/token"]
    assert out[-1] == b
    assert sorted(out) == sorted(ranked)


def test_an_auth_question_leads_with_an_auth_document() -> None:
    """Lazada "how do I sign a request": its sponsor /account/sign endpoints (contract signing)
    ranked above guide:authentication."""
    from plume.application.reader.ranking import auth_first  # noqa: PLC0415

    ranked = ["endpoint:POST~/sponsor/solutions/account/sign", "guide:resource-rules-rss",
              "guide:authentication", "endpoint:GET~/orders/get"]  # fmt: skip
    assert auth_first(ranked, 5, "how do I sign a request")[0] == "guide:authentication"
    # an operation question that only mentions a word is left alone
    signup = ["endpoint:POST~/store-api/newsletter/confirm", "guide:authentication"]
    assert auth_first(signup, 5, "finalize a subscriber sign up for the newsletter") == signup
    # an auth answer already leading stays (Magento's token endpoint)
    token = ["endpoint:POST~/{version}/integration/admin/token", "guide:authentication"]
    assert auth_first(token, 5, "how do I get an admin access token") == token


def test_with_no_auth_document_ranked_the_apis_own_comes_in() -> None:
    """TikTok "how do I sign a TikTok Shop request": only business rules and affiliate endpoints
    ranked; the app document (its signing setup) answers. A scheme first for other questions."""
    from plume.application.reader.ranking import auth_first  # noqa: PLC0415

    ranked = ["guide:resource-rules-api-9", "endpoint:GET~/affiliate_creator/shop_products"]
    own = lambda: ["auth:oauth2-authorization-code", "app:tiktokshop"]  # noqa: E731
    assert auth_first(ranked, 5, "how do I sign a TikTok Shop request", own)[0] == "app:tiktokshop"
    assert auth_first(ranked, 5, "how do I get an access token", own)[0] == (
        "auth:oauth2-authorization-code"
    )
    assert auth_first(ranked, 5, "list my warehouses", own) == ranked
