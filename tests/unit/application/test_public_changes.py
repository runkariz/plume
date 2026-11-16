"""Release notes, phase 3: the public view (confirmed/likely only, along the tagged chain)
and what newer docs mean for saved models."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from plume.application.knowledge.public_changes import ChangesInputError
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack

API = "test-catalog-api"
URL = "file:///uploaded/0162daf229a5/catalog.openapi.json"
DRAFTS = Path(__file__).resolve().parents[2] / "fixtures" / "drafts"
BASE_TEXT = "Order: id, number, customer, total, currency (ISO 4217 currency code), shop."


def _copy(packages: Path, dest: Path, page_text: str, edit: Any = None) -> Path:
    shutil.copytree(packages / "test-catalog", dest)
    if edit is not None:
        path = dest / "connector" / "models" / "order.schema.json"
        schema = json.loads(path.read_text())
        edit(schema["properties"])
        path.write_text(json.dumps(schema))
    sha = hashlib.sha256(page_text.encode()).hexdigest()
    (dest / "_sources").mkdir()
    (dest / "_sources" / f"{sha}.txt").write_text(page_text)
    (dest / "pages.json").write_text(json.dumps({"pages": [
        {"url": URL, "cleanSha256": sha, "snapshot": f"_sources/{sha}.txt", "httpStatus": 200}
    ]}))  # fmt: skip
    return dest


def _add_channel(props: dict[str, Any]) -> None:
    props["channel"] = {"type": "string", "description": "Sales channel."}


@pytest.fixture
def stack(packages: Path, tmp_path: Path) -> tuple[FakeStack, Path, Path]:
    s = FakeStack(embedder=WordEmbedder())
    s.load(str(packages / "second-catalog"))
    base = _copy(packages, tmp_path / "base", BASE_TEXT)
    s.load(str(base))
    return s, base, tmp_path


def test_confirmed_changes_are_public_and_nothing_else(
    stack: tuple[FakeStack, Path, Path], packages: Path
) -> None:
    s, _, tmp = stack
    docs = BASE_TEXT + " channel: Sales channel."
    s.load(str(_copy(packages, tmp / "a", docs, _add_channel)))
    public = s.public_changes()
    out = public.changes(API)
    assert [(i["subject"]["fieldPath"], i["op"], i["class"]) for i in out["items"]] == [
        ("channel", "added", "confirmed")
    ]
    item = out["items"][0]
    assert item["quote"] == "Sales channel."
    assert item["vendorUrl"] is None  # file:// is never a public link
    assert item["documentUrl"].startswith(f"/v1/apis/{API}/documents/model:order?version=")
    assert out["totals"]["confirmed"] == 1
    assert {"artifactRules", "evidence", "computedClass"}.isdisjoint(item)
    updated = public.docs_updated(API)
    assert updated is not None
    assert (updated["confirmed"], updated["breaking"]) == (1, 0)
    assert [t["latest"] for t in public.timeline(API)] == [True]


def test_extraction_problems_and_rolled_back_builds_are_never_public(
    stack: tuple[FakeStack, Path, Path], packages: Path
) -> None:
    s, _, tmp = stack
    bug = _copy(packages, tmp / "bug", BASE_TEXT, lambda p: p.pop("shop"))  # page unchanged
    b = s.load(str(bug))
    public = s.public_changes()
    assert public.changes(API)["items"] == []  # the removal is a suspect: hidden
    assert public.changes(API)["totals"]["confirmed"] == 0
    assert public.docs_updated(API) is None
    s.release_notes().rollback(API, b, "extraction bug")
    assert public.timeline(API) == []  # latest is the base again (no notes)


def test_since_and_filters(stack: tuple[FakeStack, Path, Path], packages: Path) -> None:
    s, _, tmp = stack
    a = s.load(str(_copy(packages, tmp / "a", BASE_TEXT + " channel: Sales channel.",
                         _add_channel)))  # fmt: skip
    public = s.public_changes()
    today = public.timeline(API)[0]["docsAsOf"]
    assert public.changes(API, since=today)["builds"] == [a]
    assert public.changes(API, since=a)["builds"] == []  # since a build: after it
    assert public.changes(API, since="2999-01-01")["items"] == []
    assert public.changes(API, breaking=True)["items"] == []
    assert public.changes(API, kind="property", q="chan")["matched"] == 1
    assert public.changes(API, kind="param, property")["matched"] == 1  # a comma list
    assert public.changes(API, kind="param,endpoint")["matched"] == 0
    with pytest.raises(ChangesInputError):
        public.changes(API, build=a, since=today)
    with pytest.raises(ChangesInputError):
        public.changes(API, build="b-nope")


def _order_model(s: FakeStack) -> Any:
    models = s.models()
    draft = json.loads((DRAFTS / "catalog-order-good.json").read_text())
    session = models.start([API, "second-catalog-api"], "Order")
    return models.submit(session.session_id, draft, maintainer=True).snapshot


def test_model_impact(stack: tuple[FakeStack, Path, Path], packages: Path) -> None:
    s, _, tmp = stack
    model = _order_model(s)
    impact = s.model_impact()
    assert impact.of_model(model)["status"] == "current"
    # a visible change the model does not cite: updated, unaffected
    s.load(str(_copy(packages, tmp / "a", BASE_TEXT + " channel: Sales channel.",
                     _add_channel)))  # fmt: skip
    assert impact.of_model(model)["status"] == "updated_unaffected"
    # the vendor removed `currency`, which the model maps: affected, breaking
    gone = BASE_TEXT.replace(", currency (ISO 4217 currency code)", "") + " channel: Sales channel."

    def channel_without_currency(props: dict[str, Any]) -> None:
        _add_channel(props)
        props.pop("currency")

    s.load(str(_copy(packages, tmp / "c", gone, channel_without_currency)))
    out = impact.of_model(model)
    assert (out["status"], out["breakingCount"]) == ("affected", 1)
    assert {a["field"] for a in out["affected"]} == {"currency"}
