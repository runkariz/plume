# ruff: noqa: E501
"""GET /v1/apis from the list's read model (a few queries for all APIs) is the same as one API
at a time; the release notes' card projection gives the same counts as the whole notes."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from plume.application.knowledge.public_changes import PublicChanges
from plume.application.reader.use_cases import ListApiOverviews
from plume.bootstrap.container import Container
from plume.bootstrap.servers import http_app
from plume.infrastructure.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
def container(clean_engine: Engine, pg_url: str, packages: Path) -> Iterator[Container]:
    c = Container(settings=Settings(database_url=pg_url, embedder="hash"))
    for name in ("shopify-mini", "test-catalog", "second-catalog"):
        c.build_pipeline().execute("job", str(packages / name))
    yield c
    c.engine.dispose()


def _one_at_a_time(c: Container) -> ListApiOverviews:
    return ListApiOverviews(c.apis, c.builds, c.tags, c.search_index, c.evals, c.assets)


def test_the_read_model_gives_the_same_overviews(container: Container) -> None:
    bulk = container.overviews().execute()
    assert bulk == _one_at_a_time(container).execute()
    with container.engine.begin() as conn:  # an API without a latest tag: no published build
        conn.execute(text("DELETE FROM tags WHERE api_id = 'shopify' AND name = 'latest'"))
    bulk = container.overviews().execute()
    assert bulk == _one_at_a_time(container).execute()
    assert next(o for o in bulk if o.info.api_id.value == "shopify").ref is None


def test_the_list_route_matches_one_api_at_a_time(container: Container) -> None:
    listed = TestClient(http_app(container)).get("/v1/apis").json()["items"]
    expected = [o.info.api_id.value for o in _one_at_a_time(container).execute()]
    assert [i["id"] for i in listed] == expected
    assert all("docsUpdated" in i for i in listed)


def _note(api: str, to: str, base: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"api": api, "to": to, "from": base, "computedAt": "2026-11-23T00:00:00+00:00",
            "review": "kept", "toDocsAsOf": "2026-11-23", "items": items}  # fmt: skip


def test_card_notes_give_the_same_counts_as_the_whole_notes(container: Container) -> None:
    latest = {a: container.resolver().resolve(a).build.build_id.value
              for a in ("shopify", "test-catalog-api")}  # fmt: skip
    item = {"subject": {"docId": "model:order", "fieldPath": "x"}, "op": "added",
            "kind": "property", "quote": "long text " * 200}  # fmt: skip
    items = [
        {**item, "class": "confirmed", "breaking": False, "wordingOnly": False, "visibleToUsers": True},
        {**item, "class": "likely", "breaking": True, "wordingOnly": False, "visibleToUsers": True},
        {**item, "class": "confirmed", "breaking": False, "wordingOnly": True, "visibleToUsers": True},
        {**item, "class": "confirmed", "breaking": True, "wordingOnly": False, "visibleToUsers": False},
    ]  # fmt: skip
    repo = container.release_notes_repo
    base = container.resolver().resolve("second-catalog-api").build.build_id.value
    repo.save(_note("shopify", latest["shopify"], base, items))
    repo.save(
        _note("test-catalog-api", latest["test-catalog-api"], base, items[3:])
    )  # nothing visible
    public = PublicChanges(repo, container.tags)
    many = public.docs_updated_many(latest)
    assert many == {a: public.docs_updated(a) for a in latest}
    assert many["shopify"] == {"build": latest["shopify"], "at": "2026-11-23", "confirmed": 1,
                               "likely": 1, "breaking": 1}  # fmt: skip
    assert many["test-catalog-api"] is None
    card = repo.card_notes([latest["shopify"]])[latest["shopify"]]
    assert len(json.dumps(card)) < 1000  # the projection, not the quotes


def test_a_note_without_a_stored_card_is_projected_from_its_body(container: Container) -> None:
    """Rows saved before migration 0022 (card NULL) still give their card, the old way."""
    from sqlalchemy import text  # noqa: PLC0415

    build = container.resolver().resolve("shopify").build.build_id.value
    base = container.resolver().resolve("second-catalog-api").build.build_id.value
    visible = {"subject": {"docId": "model:order"}, "op": "added", "kind": "property",
               "class": "confirmed", "breaking": False, "wordingOnly": False,
               "visibleToUsers": True}  # fmt: skip
    hidden = {**visible, "visibleToUsers": False}
    repo = container.release_notes_repo
    repo.save(_note("shopify", build, base, [visible, hidden]))
    stored = repo.card_notes([build])[build]
    with container.engine.begin() as conn:
        conn.execute(text("UPDATE release_notes SET card = NULL WHERE to_build = :b"), {"b": build})
    assert repo.card_notes([build])[build] == stored
    assert [i["class"] for i in stored["items"]] == ["confirmed"]
