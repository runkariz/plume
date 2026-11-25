"""A top-k of guides only gets the best endpoint for the question right after it (k + 1), from
the pool or from the endpoint-only ranking; the top-k itself never changes."""

from plume.application.reader.ranking import endpoint_after_window

GUIDES = [f"guide:g{i}" for i in range(8)]


def test_an_endpoint_from_the_wider_ranking_comes_right_after_the_window() -> None:
    out = endpoint_after_window(GUIDES, 5, lambda: ["endpoint:POST~/localized_items_batch"])
    assert out[:5] == GUIDES[:5]
    assert out[5] == "endpoint:POST~/localized_items_batch"
    assert out[6:] == GUIDES[5:]


def test_a_pool_endpoint_just_below_moves_up_without_the_wider_ranking() -> None:
    ranked = [*GUIDES[:6], "endpoint:GET~/x", *GUIDES[6:]]
    out = endpoint_after_window(ranked, 5, lambda: ["endpoint:GET~/other"])
    assert out == [*GUIDES[:5], "endpoint:GET~/x", *GUIDES[5:]]


def test_a_window_with_an_endpoint_is_left_alone() -> None:
    ranked = ["guide:a", "endpoint:GET~/x", *GUIDES]
    assert endpoint_after_window(ranked, 5, lambda: ["endpoint:GET~/y"]) == ranked


def test_nothing_to_bring_leaves_the_order() -> None:
    assert endpoint_after_window(GUIDES, 5, lambda: []) == GUIDES
    assert endpoint_after_window(GUIDES[:5], 5, lambda: ["endpoint:GET~/y"]) == GUIDES[:5]
