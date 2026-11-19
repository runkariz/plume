"""Model sets: members, relations validated against members and builds, versions, release (D3)."""

import json
from pathlib import Path
from typing import Any

import pytest

from plume.application.errors import NotFoundError
from plume.application.models.sessions import ModelDraftRefusedError, ModelStateError
from plume.domain.shared.ids import BuildId
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

DRAFTS = Path(__file__).resolve().parents[2] / "fixtures" / "drafts"
APIS = ["test-catalog-api", "second-catalog-api"]
PRODUCTS = "endpoint:GET~/api/{version}/products"


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    for p in ("test-catalog", "second-catalog"):
        s.load(str(packages / p))
    return s


def _quote(stack: FakeStack, build: str, field: str) -> str:
    doc = stack.documents.get_document(BuildId(build), PRODUCTS)
    assert doc is not None
    return next(f for f in doc.fields if f.name == field).description or ""


def _cite(stack: FakeStack, pins: dict[str, str], field: str) -> dict[str, Any]:
    return {
        api: {
            "paths": [{"path": field}],
            "evidence": [{"doc_id": PRODUCTS, "quote": _quote(stack, b, field)}],
        }
        for api, b in pins.items()
    }


def _order(stack: FakeStack, pins: dict[str, str]) -> dict[str, Any]:
    draft: dict[str, Any] = json.loads((DRAFTS / "catalog-order-good.json").read_text())
    draft["fields"].append(
        {
            "name": "items",
            "type": "array",
            "description": "Products of the order.",
            "fields": [
                {"name": "id", "type": "string", "sources": _cite(stack, pins, "items[].id")}
            ],
        }
    )
    return draft


def _product(stack: FakeStack, pins: dict[str, str]) -> dict[str, Any]:
    return {
        "name": "Product",
        "fields": [
            {"name": "id", "type": "string", "sources": _cite(stack, pins, "items[].id")},
            {"name": "name", "type": "string", "sources": _cite(stack, pins, "items[].name")},
        ],
    }


def _relation(stack: FakeStack, pins: dict[str, str], **over: Any) -> dict[str, Any]:
    rel = {
        "id": "order-items",
        "from": "Order",
        "to": "Product",
        "kind": "embedded",
        "cardinality": "1:n",
        "embed": {"field": "items"},
        "confirmed": True,
        "sources": {
            api: {
                "as": "nested",
                "paths": ["items[].id"],
                "evidence": [{"doc_id": PRODUCTS, "quote": _quote(stack, b, "items[].id")}],
            }
            for api, b in pins.items()
        },
    }
    rel.update(over)
    return rel


def _setup(
    stack: FakeStack, maintainer: bool = False
) -> tuple[Any, dict[str, str], dict[str, str]]:
    sets = stack.model_sets()
    session = sets.start(APIS, ["Order", "product"], "maintainer" if maintainer else "user")
    pins = {i.api: i.build for i in session.inputs}
    member_sessions = dict(session.member_sessions)
    models = stack.models()
    ids = {
        "Order": models.submit(
            member_sessions["Order"], _order(stack, pins), maintainer=maintainer
        ).snapshot.snapshot_id,
        "Product": models.submit(
            member_sessions["Product"], _product(stack, pins), maintainer=maintainer
        ).snapshot.snapshot_id,
    }
    return session, pins, ids


def _set(ids: dict[str, str], *relations: dict[str, Any]) -> dict[str, Any]:
    return {"name": "Shop", "members": ids, "relations": list(relations)}


def test_set_session_and_context(stack: FakeStack) -> None:
    sets = stack.model_sets()
    session = sets.start(APIS, ["Order", "order", "Product"])
    assert session.concepts == ("Order", "Product")  # normalised, de-duplicated
    ctx = sets.context(session.session_id)
    assert [m["concept"] for m in ctx["members"]] == ["Order", "Product"]
    assert all(m["session_id"].startswith("s-") for m in ctx["members"])
    assert "ASK THE USER" in ctx["instructions"]
    assert ctx["draft_format"]["relations"][0]["kind"] == "embedded"
    with pytest.raises(Exception, match=r"1\.\.8"):
        sets.start(APIS, [f"c{i}" for i in range(9)])


def test_user_set_unlisted_in_my_models_link_and_versions(stack: FakeStack) -> None:
    sets = stack.model_sets()
    session, pins, ids = _setup(stack)
    result = sets.submit(session.session_id, _set(ids, _relation(stack, pins)))
    x = result.snapshot
    assert (x.visibility, x.version, x.set_id[:3]) == ("unlisted", 1, "us-")
    assert result.owner_key is None  # no more owner keys: the My models link
    assert result.collection is not None
    link = result.collection.collection_id
    assert sets.visible(x.set_id) == x
    assert sets.list() == []
    assert [m.set_id for m in stack.collections().content(link).sets] == [x.set_id]
    assert stack.sets_repo.sets_using(ids["Order"]) == [x.set_id]
    revision = sets.revise(x.set_id)
    assert revision["members_current"] == {"Order": True, "Product": True}
    v2 = sets.submit(
        revision["set_session_id"],
        {**_set(ids, _relation(stack, pins)), "description": "v2"},
        based_on=x.set_id,
        collection=link,
    ).snapshot
    assert (v2.lineage, v2.version) == (x.set_id, 2)
    assert sets.lineage_info(v2)["versions"] == 2
    assert [m.set_id for m in stack.collections().content(link).sets] == [v2.set_id]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"to": "Nothing"}, "RELATION_END_NOT_FOUND"),
        ({"embed": {"field": "lines"}}, "RELATION_FIELD_NOT_FOUND"),
        ({"cardinality": "1:1"}, "RELATION_SHAPE_MISMATCH"),
        (
            {"kind": "reference", "ref": {"field": "customer", "key": "sku"}},
            "RELATION_FIELD_NOT_FOUND",
        ),
        ({"sources": {}}, "NO_SOURCES"),
        ({"sources": {"shopify": {"as": "nested", "paths": [], "evidence": []}}}, "API_NOT_IN_SET"),
    ],
)
def test_relation_refusals(stack: FakeStack, change: dict[str, Any], code: str) -> None:
    session, pins, ids = _setup(stack)
    with pytest.raises(ModelDraftRefusedError) as exc:
        stack.model_sets().submit(session.session_id, _set(ids, _relation(stack, pins, **change)))
    assert code in [i.code for i in exc.value.issues]


def test_relation_evidence_is_checked_like_fields(stack: FakeStack) -> None:
    session, pins, ids = _setup(stack)
    rel = _relation(stack, pins)
    api = APIS[0]
    rel["sources"][api]["evidence"][0]["quote"] = "invented text"
    rel["sources"][APIS[1]]["paths"] = ["items[].nope"]
    with pytest.raises(ModelDraftRefusedError) as exc:
        stack.model_sets().submit(session.session_id, _set(ids, rel))
    assert sorted((i.code, i.api) for i in exc.value.issues) == [
        ("FIELD_NOT_FOUND", APIS[1]),
        ("QUOTE_NOT_FOUND", api),
    ]


def test_member_rules(stack: FakeStack, packages: Path, tmp_path: Path) -> None:
    import shutil  # noqa: PLC0415

    session, pins, ids = _setup(stack)  # user (unlisted) members
    sets = stack.model_sets()
    with pytest.raises(ModelDraftRefusedError) as exc:  # a maintainer set can't use unlisted
        sets.submit(session.session_id, _set(ids, _relation(stack, pins)), maintainer=True)
    assert {i.code for i in exc.value.issues} == {"MEMBER_NOT_VISIBLE"}
    swapped = {"Order": ids["Product"], "Product": ids["Order"]}
    with pytest.raises(ModelDraftRefusedError) as exc:
        sets.submit(session.session_id, _set(swapped))
    assert {i.code for i in exc.value.issues} == {"MEMBER_CONCEPT_MISMATCH"}
    copy = tmp_path / "catalog-v2"
    shutil.copytree(packages / "test-catalog", copy)
    (copy / "connector" / "models" / "error.schema.json").unlink()
    stack.load(str(copy))  # a new build: a new set session pins it, the members do not
    fresh = sets.start(APIS, ["Order", "Product"])
    with pytest.raises(ModelDraftRefusedError) as exc:
        sets.submit(fresh.session_id, _set(ids))
    assert {i.code for i in exc.value.issues} == {"MEMBER_STALE"}


def test_maintainer_release_needs_decisions_and_releases_members(stack: FakeStack) -> None:
    sets = stack.model_sets()
    session, pins, ids = _setup(stack, maintainer=True)
    undecided = sets.submit(
        session.session_id,
        _set(ids, _relation(stack, pins, confirmed=False)),
        maintainer=True,
    ).snapshot
    assert undecided.visibility == "unreleased"
    assert undecided.undecided == ["order-items"]
    with pytest.raises(NotFoundError):
        sets.visible(undecided.set_id)  # unreleased: maintainers only
    with pytest.raises(ModelStateError, match="not decided"):
        sets.release(undecided.set_id)
    decided = sets.submit(
        session.session_id, _set(ids, _relation(stack, pins)), based_on=undecided.set_id,
        maintainer=True,
    ).snapshot  # fmt: skip
    assert (decided.lineage, decided.version) == (undecided.set_id, 2)
    released = sets.release(decided.set_id)
    assert released.snapshot.visibility == "official"
    assert sorted(released.released_members) == sorted(ids.values())
    assert all(stack.models().snapshot(i).visibility == "official" for i in ids.values())
    assert [x.set_id for x in sets.list()] == [decided.set_id]
    with pytest.raises(ModelStateError):
        sets.release(decided.set_id)
    assert sets.discard(undecided.set_id).visibility == "discarded"


def test_accepted_aliases_are_validated_stored_and_passed_to_members(stack: FakeStack) -> None:
    from plume.application.models.concepts import ModelInputError  # noqa: PLC0415

    sets = stack.model_sets()
    alias = [{"concept": "product", "names": {APIS[1]: "items"}}]
    session = sets.start(APIS, ["Order", "Product"], aliases=alias)
    assert session.aliases_json() == [{"concept": "Product", "names": {APIS[1]: "items"}}]
    member = stack.models_repo.get_session(dict(session.member_sessions)["Product"])
    assert member is not None
    assert member.name_in(APIS[1]) == "items"
    assert member.name_in(APIS[0]) == "Product"
    ctx = sets.context(session.session_id)
    assert ctx["accepted_aliases"] == session.aliases_json()
    product = next(m for m in ctx["members"] if m["concept"] == "Product")
    second = next(a for a in product["apis"] if a["api"] == APIS[1])
    assert second["searched_as"] == "items"
    assert sets.session_status(session.session_id)["aliases"] == session.aliases_json()
    for bad in (
        [{"concept": "Nope", "names": {APIS[0]: "x"}}],
        [{"concept": "Product", "names": {"shopify": "x"}}],
        [{"concept": "Product"}],
    ):
        with pytest.raises(ModelInputError):
            sets.start(APIS, ["Order", "Product"], aliases=bad)


def test_set_release_runs_the_model_gold_gate_on_its_members(stack: FakeStack) -> None:
    from plume.application.models.sessions import ModelSessions  # noqa: PLC0415

    session, pins, ids = _setup(stack, maintainer=True)
    decided = (
        stack.model_sets()
        .submit(session.session_id, _set(ids, _relation(stack, pins)), maintainer=True)
        .snapshot
    )
    plain = stack.models

    def gated() -> ModelSessions:
        s = plain()
        s._release_gate = lambda snap: [f"gold.json: 1 invented mapping(s): {snap.concept}"]
        return s

    stack.models = gated  # type: ignore[method-assign]
    with pytest.raises(ModelStateError, match=r"fails the model gold gate: gold\.json"):
        stack.model_sets().release(decided.set_id)
    assert all(plain().snapshot(i).visibility == "unreleased" for i in ids.values())
