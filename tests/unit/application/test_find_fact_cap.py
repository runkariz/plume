"""find_fact answers in bounded pages: at most 50 matches (or fewer, when one page's matches
pass the byte backstop), the total, a cursor and a hint; a lookup the database gives up on is
"too broad"."""

from pathlib import Path
from typing import Any

import pytest

import plume.application.reader.use_cases as uc
from plume.application.ports.search_index import QueryTooBroadError
from plume.application.reader.use_cases import FIND_FACT_LIMIT, ReaderInputError
from tests.fakes.stack import FakeStack


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack()
    s.load(str(packages / "shopify-mini"))
    return s


def _walk(stack: FakeStack, **kw: Any) -> tuple[list[str], int]:
    find = stack.find_fact()
    first = find.execute("shopify", "id", **kw)
    keys = [f"{m.owner_id}|{m.name}|{m.location}" for m in first.matches]
    cursor = first.next_cursor
    while cursor:
        page = find.execute("shopify", "id", cursor=cursor, **kw)
        assert page.total == first.total
        keys += [f"{m.owner_id}|{m.name}|{m.location}" for m in page.matches]
        cursor = page.next_cursor
    return keys, first.total


def test_pages_are_capped_and_the_cursor_walks_them(stack: FakeStack) -> None:
    find = stack.find_fact()
    first = find.execute("shopify", "id", limit=3)
    assert len(first.matches) == 3
    assert first.total > 3
    assert first.next_cursor
    assert first.hint is not None
    assert "owner=" in first.hint
    keys, total = _walk(stack, limit=3)
    assert len(keys) == total
    assert len(set(keys)) == total
    assert find.execute("shopify", "id", limit=500).matches.__len__() <= FIND_FACT_LIMIT
    with pytest.raises(ReaderInputError, match="cursor"):
        find.execute("shopify", "id", cursor="not-a-cursor")


def test_the_byte_backstop_moves_the_rest_to_the_next_page(
    stack: FakeStack, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(uc, "FIND_FACT_MAX_BYTES", 1)  # every page: one match
    first = stack.find_fact().execute("shopify", "id")
    assert len(first.matches) == 1
    assert first.next_cursor
    keys, total = _walk(stack)
    assert len(keys) == total
    assert len(set(keys)) == total


def test_a_lookup_the_database_gives_up_on_is_too_broad(stack: FakeStack) -> None:
    def give_up(*_a: Any, **_k: Any) -> Any:
        raise QueryTooBroadError("canceling statement due to statement timeout")

    stack.fact_query.find_page = give_up  # type: ignore[method-assign]
    with pytest.raises(ReaderInputError, match="too broad"):
        stack.find_fact().execute("shopify", "id")


def test_a_full_lookup_limit_answers_busy(stack: FakeStack) -> None:
    from plume.application.reader.use_cases import (  # noqa: PLC0415
        FindFact,
        LookupLimit,
        ReaderBusyError,
    )

    limit = LookupLimit(1, wait=0.05)
    find = FindFact(stack.resolver(), stack.fact_query, stack.search_index, stack.documents, limit)
    with limit, pytest.raises(ReaderBusyError, match="busy"):  # the one slot is taken
        find.execute("shopify", "id")
    assert find.execute("shopify", "id").matches  # free again


def test_the_cursor_carries_the_total_and_old_cursors_still_page(stack: FakeStack) -> None:
    import base64  # noqa: PLC0415
    import json  # noqa: PLC0415

    find = stack.find_fact()
    first = find.execute("shopify", "id", limit=2)
    assert first.next_cursor is not None
    key = json.loads(
        base64.urlsafe_b64decode(first.next_cursor + "=" * (-len(first.next_cursor) % 4))
    )
    assert key[-1] == first.total
    old = base64.urlsafe_b64encode(json.dumps(key[:4]).encode()).decode().rstrip("=")  # v2.1
    second = find.execute("shopify", "id", limit=2, cursor=old)
    assert second.matches
    assert second.total == first.total - 2  # a v2.1 cursor: what is left from that page on
