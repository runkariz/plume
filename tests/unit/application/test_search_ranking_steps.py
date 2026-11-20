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


def test_a_state_change_question_leads_with_the_operation_that_makes_it() -> None:
    """Shopware "mark a delivery as shipped": its transition endpoint ranked nowhere among
    thousands of CRUD endpoints; found by path among all of them."""
    from plume.application.reader.ranking import state_change_first  # noqa: PLC0415

    transition = "endpoint:POST~/api/_action/order_delivery/{orderDeliveryId}/state/{transition}"
    pay = "endpoint:POST~/store-api/order/payment"
    ranked = ["endpoint:PATCH~/api/order-delivery/{id}", "endpoint:POST~/api/order-delivery"]
    every = [*ranked, pay, transition, "endpoint:GET~/api/order-delivery/{id}/state"]
    assert state_change_first(ranked, 5, "mark a delivery as shipped", lambda: every)[0] == (
        transition
    )
    # "paid" alone is no state change of an order transaction (no noun in /order/payment)
    tx = "endpoint:POST~/api/_action/order_transaction/{orderTransactionId}/state/{transition}"
    out = state_change_first([pay], 5, "mark an order transaction as paid", lambda: [pay, tx])
    assert out[0] == tx
    mirakl = ["endpoint:PUT~/api/orders/{order_id}/ship", "model:x"]
    assert state_change_first(mirakl, 5, "mark an order as shipped", lambda: mirakl) == mirakl
    assert state_change_first(ranked, 5, "list deliveries", lambda: every) == ranked


def test_a_synthesized_guide_gives_way_to_the_vendors() -> None:
    """bol "verify the signature of a webhook": Plume's webhook-delivery guide took rank 1 above
    bol's signature-verification guide; with no vendor guide (Shopify) it stays first."""
    from plume.application.reader.ranking import synthesized_after_vendor  # noqa: PLC0415

    ours = "guide:webhook-delivery-post-retailer-subscriptions-v11"
    vendor = "guide:validation-subscriptions-digital-signature-verification"
    ranked = [ours, vendor, "endpoint:POST~/retailer/subscriptions"]
    assert synthesized_after_vendor(ranked, 5) == [vendor, ours, ranked[2]]
    alone = [ours, "endpoint:POST~/webhooks.json"]
    assert synthesized_after_vendor(alone, 5) == alone


def test_a_test_endpoint_gives_way_to_its_production_twin() -> None:
    """Trendyol "mark a package as shipped": the staging-only test PUT ranked first."""
    from plume.application.reader.ranking import production_before_test  # noqa: PLC0415

    test = "endpoint:PUT~/integration/test/order/sellers/{sellerId}/shipment-packages/{id}"
    prod = "endpoint:PUT~/integration/order/sellers/{sellerId}/shipment-packages/{id}"
    ranked = [test, "guide:x", prod]
    assert production_before_test(ranked, "mark a package as shipped") == [prod, test, "guide:x"]
    assert production_before_test(ranked, "mark a package as shipped in the test environment") == (
        ranked
    )
    assert production_before_test([test, "guide:x"], "mark shipped") == [test, "guide:x"]


def test_a_webhook_auth_guide_is_not_the_auth_answer() -> None:
    """Trendyol "how do I authenticate": the webhook auth guide led, the Basic scheme was 7th."""
    from plume.application.reader.ranking import auth_first  # noqa: PLC0415

    ranked = ["guide:webhooks-authentication", "endpoint:GET~/x", "auth:basic"]
    assert auth_first(ranked, 5, "how do I authenticate my api calls")[0] == "auth:basic"
    assert auth_first(ranked, 5, "how do I authenticate?")[0] == "auth:basic"
    assert auth_first(ranked, 5, "how do I authenticate a returning customer at checkout") == (
        ranked  # an operation question that only uses the word
    )


def test_a_path_only_endpoint_follows_the_endpoints_it_serves() -> None:
    """Mirakl GET /{file_path}@get-tl05 (an export file chunk) ranked 1 for invoices."""
    from plume.application.reader.ranking import path_only_after_endpoints  # noqa: PLC0415

    chunk = "endpoint:GET~/{file_path}@get-tl05"
    invoices = "endpoint:GET~/api/invoices"
    assert path_only_after_endpoints([chunk, "guide:x", invoices], 5) == [
        "guide:x", invoices, chunk,
    ]  # fmt: skip
    assert path_only_after_endpoints([chunk, "guide:x"], 5) == [chunk, "guide:x"]


def test_a_rate_limit_question_leads_with_a_rate_limit_guide() -> None:
    from plume.application.reader.ranking import rate_limit_guide_first  # noqa: PLC0415

    ranked = ["guide:resource-rules-api-2", "endpoint:GET~/api/orders", "guide:rate-limits"]
    assert rate_limit_guide_first(ranked, 5, "what does a 429 mean")[0] == "guide:rate-limits"
    assert rate_limit_guide_first(ranked, 5, "list orders") == ranked


def test_a_scope_question_leads_with_the_auth_scheme() -> None:
    """Allegro "which scope do I need to read orders": guide:authentication led, the scheme
    (it lists the scopes) was 6th."""
    from plume.application.reader.ranking import auth_first  # noqa: PLC0415

    ranked = ["guide:authentication", "endpoint:GET~/order/events"]
    own = lambda: ["auth:oauth2-authorization-code"]  # noqa: E731
    assert auth_first(ranked, 5, "which scope do I need to read orders", own)[0] == (
        "auth:oauth2-authorization-code"
    )


def test_an_endpoint_goes_before_its_resources_model() -> None:
    """Amazon "register an SQS destination": model:destination above POST /destinations."""
    from plume.application.reader.ranking import endpoint_before_its_model  # noqa: PLC0415

    post = "endpoint:POST~/notifications/{version}/destinations"
    ranked = ["model:destination", post, "model:sqsresource"]
    assert endpoint_before_its_model(ranked, 5) == [post, "model:destination", "model:sqsresource"]
    get = "endpoint:GET~/orders/{version}/orders/{orderId}"
    assert endpoint_before_its_model(["model:order", get], 5) == [get, "model:order"]
    other = ["model:order", "endpoint:GET~/customers"]
    assert endpoint_before_its_model(other, 5) == other
