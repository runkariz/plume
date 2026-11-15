import json
from pathlib import Path
from typing import Any

import pytest

from plume.application.errors import NotFoundError
from plume.application.models.concepts import ModelInputError, concept_key
from plume.application.models.sessions import ModelDraftRefusedError
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

DRAFTS = Path(__file__).resolve().parents[2] / "fixtures" / "drafts"
APIS = ["test-catalog-api", "second-catalog-api"]


def _draft(name: str) -> dict[str, Any]:
    return json.loads((DRAFTS / f"catalog-order-{name}.json").read_text())  # type: ignore[no-any-return]


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    for p in ("test-catalog", "second-catalog", "shopify-mini"):
        s.load(str(packages / p))
    return s


def test_concept_keys() -> None:
    assert concept_key("Orders") == concept_key("order") == "order"
    assert concept_key("Categories") == "category"
    assert concept_key("DraftOrder") == "draftorder"
    assert concept_key("address") == "address"


def test_suggest_concepts(stack: FakeStack) -> None:
    s = stack.suggest().execute(APIS)
    keys = [c.key for c in s.concepts]
    assert keys[:2] == ["order", "product"] or keys[:2] == ["product", "order"]
    order = next(c for c in s.concepts if c.key == "order")
    assert order.coverage == {"test-catalog-api": "direct", "second-catalog-api": "direct"}
    assert order.difficulty == ("ok", "Straightforward")
    assert order.likely_fields >= 6
    assert "read" in order.operations
    assert "model:order" in order.doc_ids["test-catalog-api"]
    assert "error" not in keys  # noise


def test_suggest_with_partial_coverage(stack: FakeStack) -> None:
    s = stack.suggest().execute(["shopify", "test-catalog-api"])
    product = next(c for c in s.concepts if c.key == "product")
    assert product.coverage["shopify"] == "direct"
    assert s.not_modeled > 0


def test_suggest_validation(stack: FakeStack) -> None:
    with pytest.raises(ModelInputError):
        stack.suggest().execute(["shopify"])
    with pytest.raises(ModelInputError):
        stack.suggest().execute(["shopify", "shopify"])
    with pytest.raises(NotFoundError):
        stack.suggest().execute(["shopify", "nope"])


def test_session_context_index_and_paged_evidence(stack: FakeStack) -> None:
    session = stack.models().start(APIS, "Order")
    assert [i.api for i in session.inputs] == APIS
    ctx = stack.models().context(session.session_id)
    assert ctx["concept"] == "Order"
    apis = {a["api"]: a for a in ctx["apis"]}
    docs = apis["test-catalog-api"]["documents"]
    assert docs[0]["doc_id"] == "model:order"  # models first
    assert docs[0]["fields"] == 6  # a count, not the fields
    assert "get_model_evidence" in ctx["instructions"]
    assert ctx["draft_format"]["fields"][0]["sources"]

    ev = stack.models().evidence(session.session_id, "test-catalog-api")
    paths = {f["path"] for d in ev["documents"] for f in d["fields"]}
    assert {"total", "orders[].total"} <= paths
    assert ev["next_cursor"] is None
    assert ev["returned"] == ev["total_fields"]
    one = stack.models().evidence(session.session_id, "test-catalog-api", ["model:order", "x:y"])
    assert [d["doc_id"] for d in one["documents"]] == ["model:order"]
    assert one["missing_doc_ids"] == ["x:y"]
    with pytest.raises(NotFoundError):
        stack.models().context("s-nope")
    with pytest.raises(ModelInputError):
        stack.models().evidence(session.session_id, "shopify")


def test_evidence_pages_stay_under_budget(stack: FakeStack) -> None:
    session = stack.models().start(["shopify", "test-catalog-api"], "Product")
    ctx = stack.models().context(session.session_id)
    assert len(json.dumps(ctx)) < 25_000
    seen: list[str] = []
    cursor: int | None = 0
    pages = 0
    while cursor is not None:
        page = stack.models().evidence(
            session.session_id, "shopify", cursor=cursor, budget_chars=2_000
        )
        assert len(json.dumps(page, ensure_ascii=False)) < 2_000 + 1_500
        seen += [f["path"] for d in page["documents"] for f in d["fields"]]
        cursor = page["next_cursor"]
        pages += 1
    assert pages > 1
    assert len(seen) == page["total_fields"]  # every field exactly once across pages


def test_good_draft_becomes_an_immutable_snapshot(stack: FakeStack) -> None:
    models = stack.models()
    session = models.start(APIS, "Order")
    result = models.submit(session.session_id, _draft("good"), maintainer=True)
    assert result.created
    snap = result.snapshot
    assert snap.status == "generated_unverified"
    assert snap.visibility == "unreleased"
    assert snap.citations_checked == 10
    assert snap.coverage() == {"test-catalog-api": (5, 5), "second-catalog-api": (5, 5)}
    again = models.submit(session.session_id, _draft("good"), maintainer=True)
    assert not again.created
    assert again.snapshot.snapshot_id == snap.snapshot_id
    assert models.snapshot(snap.snapshot_id) == snap
    assert models.existing(APIS, "orders") is None  # unreleased: not offered publicly
    assert models.existing(APIS, "orders", maintainer=True) == snap
    assert models.list("second-catalog-api") == []
    released = models.release(snap.snapshot_id)
    assert released.visibility == "official"
    assert models.existing(APIS, "orders") == released
    assert [m.snapshot_id for m in models.list("second-catalog-api")] == [snap.snapshot_id]
    assert models.list("shopify") == []


@pytest.mark.parametrize(
    "name",
    [
        "missing-citation",
        "quote-not-in-doc",
        "field-not-in-api",
        "api-not-in-session",
        "endpoint-not-in-api",
        "doc-not-in-build",
    ],
)
def test_bad_drafts_are_refused_with_a_precise_code(stack: FakeStack, name: str) -> None:
    raw = _draft(f"bad-{name}")
    session = stack.models().start(APIS, "Order")
    with pytest.raises(ModelDraftRefusedError) as info:
        stack.models().submit(session.session_id, raw)
    assert [i.code for i in info.value.issues] == [raw["_expect_code"]]
    assert stack.models_repo.snapshots == {}


def test_format_error_is_a_refusal(stack: FakeStack) -> None:
    session = stack.models().start(APIS, "Order")
    with pytest.raises(ModelDraftRefusedError) as info:
        stack.models().submit(session.session_id, {"name": "x", "fields": []})
    assert info.value.issues[0].code == "INVALID_FORMAT"


def test_bundled_models_suggest_by_leaf_name(packages: Path) -> None:
    s = FakeStack(embedder=WordEmbedder())
    s.load(str(packages / "mirakl-mini"))
    s.load(str(packages / "shopify-mini"))
    keys = {c.key: c for c in s.suggest().execute(["mirakl", "shopify"]).concepts}
    assert keys["address"].coverage == {"mirakl": "direct", "shopify": "direct"}
    assert keys["customer"].coverage["mirakl"] == "direct"
    assert not any("response" in k for k in keys)  # bundle roots are not concepts
    counts = s.overviews().one("mirakl").counts
    assert (counts["model"], counts["model_shapes"]) == (12, 11)
    # billing info, boolean, date, link, address, customer, orders (the 2 roots are no names)
    assert counts["model_names"] == 7


def test_snapshots_go_stale_when_a_pinned_build_moves(stack: FakeStack, tmp_path: Path) -> None:
    import shutil  # noqa: PLC0415

    models = stack.models()
    session = models.start(APIS, "Order")
    sid = models.submit(session.session_id, _draft("good"), maintainer=True).snapshot.snapshot_id
    snap = models.release(sid)
    assert models.stale_inputs(snap) == []
    assert models.existing(APIS, "Order") == snap

    copy = tmp_path / "catalog-v2"
    shutil.copytree(Path(__file__).resolve().parents[2] / "fixtures/packages/test-catalog", copy)
    (copy / "connector" / "models" / "error.schema.json").unlink()
    new_build = stack.load(str(copy))
    stale = models.stale_inputs(snap)
    assert stale == [
        {"api": "test-catalog-api", "pinned": snap.inputs[0].build, "current": new_build}
    ]
    assert models.existing(APIS, "Order") is None  # generate opens a new session instead


def test_concept_spelling_is_normalised(stack: FakeStack) -> None:
    from plume.application.models.sessions import normalize_concept  # noqa: PLC0415

    assert normalize_concept("  order ") == "Order"
    assert normalize_concept("product  offer") == "Product offer"
    assert normalize_concept("Product/Offer") == "Product/Offer"
    assert normalize_concept("SKU") == "SKU"
    assert stack.models().start(APIS, "order").concept == "Order"


# -- access: unlisted user models, lineages, owner keys, release/discard ----------------------


def test_user_models_are_unlisted_with_a_random_id_and_owner_key(stack: FakeStack) -> None:
    from plume.application.errors import NotFoundError  # noqa: PLC0415

    models = stack.models()
    session = models.start(APIS, "Order", "user")
    result = models.submit(session.session_id, _draft("good"))
    snap = result.snapshot
    assert (snap.visibility, snap.origin, snap.version) == ("unlisted", "user", 1)
    assert snap.snapshot_id.startswith("u-")
    assert len(snap.snapshot_id) >= 22
    assert snap.key.startswith("m-")  # the content hash, kept for dedup only
    assert result.owner_key
    assert result.owner_key.startswith("pk_")
    retry = models.submit(session.session_id, _draft("good"))  # same draft again: same model
    assert (retry.created, retry.snapshot.snapshot_id, retry.owner_key) == (
        False,
        snap.snapshot_id,
        None,
    )
    assert models.visible_snapshot(snap.snapshot_id) == snap  # the link works for anyone
    assert models.list() == []
    assert models.existing(APIS, "Order") is None
    assert [m.snapshot_id for m in models.mine([result.owner_key])] == [snap.snapshot_id]
    assert models.mine(["pk_wrong"]) == []
    assert models.session_status(session.session_id)["snapshot_id"] == snap.snapshot_id
    other = models.submit(models.start(APIS, "Order", "user").session_id, _draft("good"))
    assert other.snapshot.snapshot_id != snap.snapshot_id  # another user, another lineage
    with pytest.raises(NotFoundError):
        models.visible_snapshot("u-guess")


def test_revisions_make_versions_in_a_lineage(stack: FakeStack) -> None:
    models = stack.models()
    first = models.submit(models.start(APIS, "Order", "user").session_id, _draft("good"))
    v1 = first.snapshot
    revision = models.revise(v1.snapshot_id)
    assert revision["based_on"] == v1.snapshot_id
    assert revision["starting_draft"]["name"] == v1.draft.name
    changed = dict(_draft("good"), description="Revised description.")
    v2 = models.submit(revision["session_id"], changed).snapshot
    assert (v2.lineage, v2.version, v2.based_on) == (v1.snapshot_id, 2, v1.snapshot_id)
    v3 = models.submit(
        models.revise(v2.snapshot_id)["session_id"],
        dict(changed, description="Third."),
        based_on=v2.snapshot_id,
    ).snapshot
    info = models.lineage_info(v3)
    assert (info["version"], info["versions"], info["latest_id"]) == (3, 3, v3.snapshot_id)
    assert [h["version"] for h in info["history"]] == [1, 2, 3]
    assert [m.snapshot_id for m in models.mine([first.owner_key or ""])] == [v3.snapshot_id]
    assert models.snapshot(v1.snapshot_id) == v1  # versions never change


def test_maintainer_flow_release_discard_and_official_forks(stack: FakeStack) -> None:
    from plume.application.errors import NotFoundError  # noqa: PLC0415
    from plume.application.models.sessions import ModelStateError  # noqa: PLC0415

    models = stack.models()
    snap = models.submit(models.start(APIS, "Order").session_id, _draft("good"), maintainer=True)
    sid = snap.snapshot.snapshot_id
    assert snap.owner_key is None
    with pytest.raises(NotFoundError):
        models.visible_snapshot(sid)  # unreleased: hidden without the token
    assert models.visible_snapshot(sid, maintainer=True).visibility == "unreleased"
    official = models.release(sid)
    with pytest.raises(ModelStateError):
        models.release(sid)
    with pytest.raises(ModelStateError):
        models.discard(sid)
    # a user revising the official model starts their own unlisted lineage
    user = models.submit(
        models.revise(sid)["session_id"], dict(_draft("good"), description="Mine.")
    )
    assert (user.snapshot.visibility, user.snapshot.version) == ("unlisted", 1)
    assert user.snapshot.lineage != official.lineage
    assert user.snapshot.based_on == sid
    assert user.owner_key
    # a maintainer revision is the next (unreleased) version of the official lineage
    v2 = models.submit(
        models.revise(sid, maintainer=True)["session_id"],
        dict(_draft("good"), description="Better."),
        maintainer=True,
    ).snapshot
    assert (v2.lineage, v2.version, v2.visibility) == (official.lineage, 2, "unreleased")
    assert models.lineage_info(official)["versions"] == 1  # public view: unreleased hidden
    assert models.lineage_info(official, maintainer=True)["versions"] == 2
    discarded = models.discard(v2.snapshot_id)
    assert discarded.visibility == "discarded"
    assert [m.snapshot_id for m in models.list()] == [sid]


def test_oversized_draft_is_refused(stack: FakeStack) -> None:
    from plume.application.models.sessions import ModelDraftRefusedError  # noqa: PLC0415

    models = stack.models()
    session = models.start(APIS, "Order", "user")
    with pytest.raises(ModelDraftRefusedError) as exc:
        models.submit(session.session_id, {"name": "x" * 1_100_000})
    assert exc.value.issues[0].code == "INVALID_FORMAT"
