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


def test_trendyol_live_cases() -> None:
    """Live Trendyol: a Turkish webhook guide ("bildirim") led API auth questions; the webhook
    auth question wants the webhook guide; the test PUT's production twin has another path."""
    from plume.application.reader.ranking import auth_first, production_before_test  # noqa: PLC0415

    turkish = (
        "guide:workflow-6-nas-c4-b1l-bildirim-olu-c5-9fturabilirim-api-authentication-configuration"
    )
    webhook = "guide:validation-webhook-model-webhook-authentication-configuration"
    ranked = [turkish, "guide:resource-rules-integration-15", webhook, "auth:basic-authorization"]
    assert auth_first(ranked, 5, "how do I authenticate with the Trendyol API")[0] == (
        "auth:basic-authorization"
    )
    assert auth_first(ranked, 5, "how does Trendyol authenticate its webhook calls to me")[0] == (
        webhook
    )
    test = "endpoint:PUT~/integration/test/order/sellers/{sellerId}/shipment-packages/{id}/status"
    prod = "endpoint:PUT~/integration/order/sellers/{sellerId}/shipment-packages/{id}"
    assert (
        production_before_test([test, "trigger:shipped", prod], "mark a package as shipped")[0]
        == prod
    )


def test_batch1b_cdon_and_back_market_cases() -> None:
    from plume.application.reader.ranking import (  # noqa: PLC0415
        request_models_last,
        state_change_first,
        synthesized_after_vendor,
    )

    fulfill = "endpoint:PUT~/{version}/orders/{order_id}/fulfill"  # CDON: fulfill = ship
    ranked = ["endpoint:GET~/{version}/orders", "model:order", fulfill]
    assert state_change_first(ranked, 5, "mark an order as shipped with tracking",
                              lambda: ranked)[0] == fulfill  # fmt: skip
    body = "model:updatearticlequantitybody"  # CDON: a request body above the endpoint
    put = "endpoint:PUT~/{version}/articles/{article_id}/quantity"
    assert request_models_last([body, put], 5) == [put, body]
    ours = "guide:environments-and-base-urls"  # Back Market: behind its own environments guide
    out = synthesized_after_vendor(
        [ours, "guide:context", "endpoint:GET~/x", "guide:environments"], 5
    )
    assert out.index("guide:environments") < out.index(ours)


def test_a_push_question_leads_with_a_webhook_document() -> None:
    """Magento "does Magento call my URL / send webhooks": the webhook endpoints were not in the
    top 8; found among all endpoints."""
    from plume.application.reader.ranking import push_first  # noqa: PLC0415

    ranked = ["guide:resource-rules-api-6", "guide:workflow-gs-curl-constructing-endpoint-urls"]
    every = ["endpoint:GET~/{version}/orders", "endpoint:POST~/{version}/webhooks/subscribe"]
    assert (
        push_first(ranked, 5, "does Magento call my URL or send webhooks", lambda: every)[0]
        == "endpoint:POST~/{version}/webhooks/subscribe"
    )
    assert push_first(ranked, 5, "list orders", lambda: every) == ranked


def test_push_lead_leaves_verification_and_context_cases() -> None:
    from plume.application.reader.ranking import (  # noqa: PLC0415
        context_after_named_endpoint,
        push_first,
    )

    # METRO "how do I verify a webhook": the HMAC request-signing guide answers
    signing = ["guide:validation-authentication-hmac-sha256-request-signing", "guide:x"]
    every = ["endpoint:POST~/webhooks/subscribe"]
    assert push_first(signing, 5, "how do I verify a webhook from METRO", lambda: every) == signing
    # BigCommerce: the overview gives way to an endpoint named by the question
    brands = "endpoint:GET~/{version}/catalog/brands/{brand_id}/metafields"
    ranked = ["guide:context", "guide:y", brands]
    assert context_after_named_endpoint(ranked, 5, "metadata for brands")[0] == brands
    assert context_after_named_endpoint(ranked, 5, "how does paging work") == ranked


def test_endpoints_go_before_the_models_they_return_on_task_questions() -> None:
    from plume.application.reader.ranking import endpoints_before_returned_models  # noqa: PLC0415

    returns = {"model:categoryview": ["endpoint:GET~/categories/{id}"],
               "model:categorybrowse": ["endpoint:GET~/categories"]}  # fmt: skip
    ranked = ["model:categoryview", "model:categorybrowse", "endpoint:GET~/categories",
              "endpoint:GET~/categories/{id}", "guide:x"]  # fmt: skip

    def lookup(model: str, pool: object) -> list[str]:
        return returns.get(model, [])

    task = endpoints_before_returned_models(
        ranked, 5, "how can I see the category mappings", lookup
    )
    assert task == ["endpoint:GET~/categories", "endpoint:GET~/categories/{id}",
                    "model:categoryview", "model:categorybrowse", "guide:x"]  # fmt: skip
    shape = endpoints_before_returned_models(ranked, 5, "what fields does a category have", lookup)
    assert shape == ranked
    deep = ["guide:a", "model:categorybrowse", "guide:b", "endpoint:GET~/categories"]
    assert endpoints_before_returned_models(deep, 2, "browse categories", lookup) == [
        "guide:a", "endpoint:GET~/categories", "model:categorybrowse", "guide:b"]  # fmt: skip
    assert endpoints_before_returned_models(["model:x", "guide:y"], 2, "q", lookup) == [
        "model:x",
        "guide:y",
    ]


def test_an_endpoint_already_above_its_model_stays() -> None:
    from plume.application.reader.ranking import endpoints_before_returned_models  # noqa: PLC0415

    def lookup(model: str, pool: object) -> list[str]:
        return ["endpoint:GET~/logs", "endpoint:GET~/lines"] if model == "model:tl02" else []

    above = ["endpoint:GET~/logs", "model:tl02", "endpoint:GET~/lines", "guide:a"]
    assert endpoints_before_returned_models(above, 5, "max page size of logs", lookup) == [
        "endpoint:GET~/logs", "endpoint:GET~/lines", "model:tl02", "guide:a"]  # fmt: skip


def test_how_to_questions_put_endpoints_before_knowledge_units() -> None:
    from plume.application.reader.ranking import endpoints_before_units_on_how_to  # noqa: PLC0415

    ranked = ["guide:page-diagnostics", "guide:page-batch-api", "endpoint:POST~/items_batch",
              "endpoint:GET~/check_batch_request_status", "guide:resource-rules-api-2"]  # fmt: skip
    out = endpoints_before_units_on_how_to(
        ranked, 5, "how do I get the list of invalid items in a batch"
    )
    assert out == [
        "endpoint:POST~/items_batch", "endpoint:GET~/check_batch_request_status",
        "guide:page-diagnostics", "guide:page-batch-api", "guide:resource-rules-api-2",
    ]  # fmt: skip
    workflow = ["guide:workflow-x", "endpoint:POST~/a", "guide:page-y"]  # a workflow stays first
    assert endpoints_before_units_on_how_to(workflow, 3, "how do I do x") == workflow
    assert endpoints_before_units_on_how_to(ranked, 5, "what is the maximum payload size") == ranked
    assert (
        endpoints_before_units_on_how_to(ranked, 5, "how do I see the fields of a batch") == ranked
    )
    vendor = ["auth:oauth2", "guide:page-x", "endpoint:POST~/a"]
    assert endpoints_before_units_on_how_to(vendor, 3, "how do I create a") == [
        "auth:oauth2", "endpoint:POST~/a", "guide:page-x"]  # fmt: skip
