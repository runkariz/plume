# ruff: noqa: E501
"""Mapping reports: the suggestion runs through the model-draft validator, dedupe on
(concept, api, field, kind), verified mappings in new sessions, suspension when a build drops
the field, redaction and limits."""

import json
import shutil
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from plume.application.models.sessions import ModelSessions
from plume.application.reports.mappings import MappingReports
from plume.application.reports.service import ReportRefusedError, ReportsDisabledError
from tests.fakes.knowledge import FakeClock, WordEmbedder
from tests.fakes.mappings import InMemoryMappings
from tests.fakes.stack import FakeStack

API = "test-catalog-api"
APIS = [API, "second-catalog-api"]
PACKAGES = Path(__file__).resolve().parents[2] / "fixtures" / "packages"
GOOD: dict[str, Any] = {"paths": ["total"], "fetch": "GET /api/{version}/orders",
        "evidence": [{"doc_id": "model:order", "quote": "Total monetary amount billed for the order."}]}  # fmt: skip


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    for p in ("test-catalog", "second-catalog"):
        s.load(str(packages / p))
    return s


def _service(stack: FakeStack, **kw: Any) -> tuple[MappingReports, InMemoryMappings]:
    repo = InMemoryMappings()
    svc = MappingReports(repo, stack.resolver(), stack.models_repo, stack.fact_query,
                         stack.documents, FakeClock(step=timedelta(seconds=1)), enabled=True,
                         salt=b"k", **kw)  # fmt: skip
    return svc, repo


def _sessions(stack: FakeStack, svc: MappingReports) -> ModelSessions:
    return ModelSessions(stack.resolver(), stack.search_index, stack.fact_query, stack.documents,
                         stack.models_repo, stack.clock, stack.collections(),
                         verified=svc.for_session)  # fmt: skip


def test_a_valid_suggestion_is_stored_and_a_failing_one_only_as_the_problem(
    stack: FakeStack,
) -> None:
    svc, repo = _service(stack)
    sid = stack.models().start(APIS, "Order").session_id
    ok = svc.report(sid, API, "grandTotal", "missing", "the total has no mapping", None, GOOD)
    assert ok["validation"] == {"ok": True, "reason": None}
    stored = repo.get(ok["id"])
    assert stored is not None
    assert stored.suggestion is not None
    assert stored.suggestion.paths == ("total",)
    assert stored.concept == "order"
    # a field that is not in the API's package
    bad_field = {**GOOD, "paths": ["grand_total_xyz"]}
    out = svc.report(sid, API, "tax", "wrong", "tax comes from the wrong field", "taxes", bad_field)
    assert out["validation"]["ok"] is False
    assert out["validation"]["reason"].startswith("FIELD_NOT_FOUND")
    assert "not stored" in out["message"]
    kept = repo.get(out["id"])
    assert kept is not None
    assert kept.suggestion is None
    assert kept.validator_reason is not None
    assert kept.validator_reason.startswith("FIELD_NOT_FOUND")
    # a quote that is not in the cited document
    bad_quote = {
        **GOOD,
        "evidence": [{"doc_id": "model:order", "quote": "The grand total including every fee."}],
    }
    out = svc.report(sid, API, "currency", "wrong", "currency is wrong", None, bad_quote)
    assert out["validation"]["reason"].startswith("QUOTE_NOT_FOUND")
    assert repo.get(out["id"]).suggestion is None  # type: ignore[union-attr]
    # a malformed suggestion is a validator reason too, never an error
    out = svc.report(sid, API, "shop", "wrong", "shop is wrong", None, {"paths": []})
    assert out["validation"]["reason"].startswith("INVALID_FORMAT")


def test_the_same_field_and_kind_adds_a_note(stack: FakeStack) -> None:
    svc, repo = _service(stack)
    sid = stack.models().start(APIS, "Order").session_id
    first = svc.report(sid, API, "items[].sku", "wrong", "sku maps to the id", "id")
    again = svc.report(sid, API, "Items.SKU", "wrong", "sku should be the article number")
    assert again["merged"] is True
    assert again["id"] == first["id"]
    other_kind = svc.report(sid, API, "items[].sku", "missing", "no sku at all")
    assert other_kind["id"] != first["id"]
    other_api = svc.report(sid, "second-catalog-api", "items[].sku", "wrong", "sku maps to the id")
    assert other_api["id"] != first["id"]
    r = repo.get(first["id"])
    assert r is not None
    assert (r.report_count, r.note_count) == (2, 1)
    assert "Also reported" in repo.notes(first["id"])[0].text
    noted = svc.add_note(first["id"], "same here")
    assert noted["report"]["report_count"] == 3
    found = svc.find(sid, API, "items[].sku")
    assert {x["id"] for x in found["reports"]} == {first["id"], other_kind["id"]}
    with pytest.raises(LookupError):
        svc.add_note("mr-nope", "x")
    with pytest.raises(LookupError):
        svc.find("s-nope", API)


def test_an_accepted_mapping_is_shown_first_in_a_new_session(stack: FakeStack) -> None:
    svc, repo = _service(stack)
    sid = stack.models().start(APIS, "Order").session_id
    rid = svc.report(sid, API, "grandTotal", "missing", "the total has no mapping", None, GOOD)[
        "id"
    ]
    with pytest.raises(ReportRefusedError, match="reason"):
        svc.act(rid, "accept")
    done = svc.act(rid, "accept", "matches the docs")
    assert done["status"] == "accepted"
    assert done["verified"]["suspended"] is False
    fresh = _sessions(stack, svc)
    new = fresh.start(APIS, "orders")  # another spelling of the concept
    ctx = {a["api"]: a for a in fresh.context(new.session_id)["apis"]}
    verified = ctx[API]["verified_mappings"]
    assert [(v["canonical_field"], v["paths"]) for v in verified] == [("grandTotal", ["total"])]
    assert verified[0]["label"] == f"verified (user report {rid})"
    assert "verified_mappings" not in ctx["second-catalog-api"]
    assert svc.find(new.session_id, API)["verified_mappings"][0]["report_id"] == rid
    # a report without a valid suggestion cannot be accepted; reject keeps the reason for readers
    other = svc.report(
        sid, API, "tax", "wrong", "tax is wrong", None, {**GOOD, "paths": ["nope_x"]}
    )["id"]
    with pytest.raises(ReportRefusedError, match="validated suggestion"):
        svc.act(other, "accept", "ok")
    svc.act(other, "reject", "the current mapping is right")
    shown = {r["id"]: r for r in svc.find(sid, API)["reports"]}
    assert shown[other]["reason"] == "the current mapping is right"
    routed = svc.act(other, "route", "not in the package", "stream")
    assert (routed["status"], routed["route"]) == ("routed", "stream")
    with pytest.raises(ReportRefusedError, match="route must be"):
        svc.act(other, "route", "x", "elsewhere")
    assert len(repo.mappings) == 1


def test_a_build_that_drops_the_field_suspends_it_and_reopens_the_report(
    stack: FakeStack, tmp_path: Path
) -> None:
    svc, repo = _service(stack)
    sid = stack.models().start(APIS, "Order").session_id
    rid = svc.report(sid, API, "grandTotal", "missing", "the total has no mapping", None, GOOD)[
        "id"
    ]
    svc.act(rid, "accept", "matches the docs")
    copy = tmp_path / "catalog-v2"
    shutil.copytree(PACKAGES / "test-catalog", copy)
    schema = copy / "connector" / "models" / "order.schema.json"
    data = json.loads(schema.read_text())
    del data["properties"]["total"]
    schema.write_text(json.dumps(data))
    stack.load(str(copy))
    fresh = _sessions(stack, svc)
    ctx = {a["api"]: a for a in fresh.context(fresh.start(APIS, "Order").session_id)["apis"]}
    assert "verified_mappings" not in ctx[API]  # suspended: not offered
    (m,) = repo.mappings.values()
    assert m.status.value == "suspended"
    assert m.suspended_reason is not None
    assert m.suspended_reason.split(":")[0] in {"FIELD_NOT_FOUND", "QUOTE_NOT_FOUND"}
    report = svc.get(rid)
    assert report["status"] == "open"
    assert "suspended" in report["reason"]
    assert report["verified"]["suspended"] is True
    assert svc.revalidate(API) == {"kept": 0, "suspended": 0, "unchanged": 1}


def test_redaction_limits_and_the_switch(stack: FakeStack) -> None:
    svc, repo = _service(stack, per_hour=2)
    sid = stack.models().start(APIS, "Order").session_id
    out = svc.report(sid, API, "customer", "wrong", "the customer john.doe@example.com shows the shop name",
                     "shop", None, "claude-code", "sess-1")  # fmt: skip
    stored = repo.get(out["id"])
    assert stored is not None
    assert "john.doe@example.com" not in stored.problem
    assert stored.redactions >= 1
    assert stored.session_hash
    assert stored.session_hash != "sess-1"
    assert stored.client_name == "claude-code"
    svc.report(sid, API, "shop", "wrong", "the shop is wrong", None, None, None, "sess-1")
    with pytest.raises(ReportRefusedError, match="last hour"):
        svc.report(
            sid, API, "currency", "wrong", "the currency is wrong", None, None, None, "sess-1"
        )
    with pytest.raises(ReportRefusedError, match="1000 characters"):
        svc.report(sid, API, "x", "wrong", "y" * 1001)
    with pytest.raises(ReportRefusedError, match="kind must be"):
        svc.report(sid, API, "x", "odd", "y")
    off, _ = _service(stack, per_hour=2)
    object.__setattr__(off, "_enabled", False)
    with pytest.raises(ReportsDisabledError):
        off.report(sid, API, "x", "wrong", "y")


ABSENT: dict[str, Any] = {
    "notAvailable": True,
    "notFrom": ["number"],
    "evidence": [{"doc_id": "model:order",
                  "quote": "Human-readable reference or tracking number for the order."}],
}  # fmt: skip
DRAFT = PACKAGES.parent / "drafts" / "catalog-order-good.json"


def test_a_documented_absence_is_validated_accepted_and_shown(stack: FakeStack) -> None:
    svc, _ = _service(stack)
    sid = stack.models().start(APIS, "Order").session_id
    ok = svc.report(sid, API, "trackingCode", "wrong", "number is not the tracking code",
                    "number", ABSENT)  # fmt: skip
    assert ok["validation"] == {"ok": True, "reason": None}
    refused = {
        "an unknown notFrom path": ({**ABSENT, "notFrom": ["nope_xyz"]}, "FIELD_NOT_FOUND"),
        "noQuote": ({**ABSENT, "evidence": [{"doc_id": "model:order", "noQuote": "absent"}]},
                    "NO_QUOTE_NOT_ALLOWED"),
        "a quote about another field": ({**ABSENT, "evidence": [{"doc_id": "model:order",
                    "quote": "Three-letter currency code for the order total."}]}, "QUOTE_NOT_ON_FIELD"),
        "no citation": ({**ABSENT, "evidence": []}, "MISSING_CITATION"),
        "paths and absence": ({**ABSENT, "paths": ["number"]}, "INVALID_FORMAT"),
    }  # fmt: skip
    for i, (why, (raw, code)) in enumerate(refused.items()):
        out = svc.report(sid, API, f"f{i}", "wrong", "x is wrong", None, raw)
        assert out["validation"]["reason"].split(":")[0] == code, why
    svc.act(ok["id"], "accept", "number is the order reference")
    fresh = _sessions(stack, svc)
    ctx = {a["api"]: a for a in fresh.context(fresh.start(APIS, "Order").session_id)["apis"]}
    (v,) = ctx[API]["verified_mappings"]
    assert (v["notAvailable"], v["notFrom"], v["paths"]) == (True, ["number"], [])
    assert "Not available on this API" in v["note"]


def test_a_draft_that_contradicts_a_verified_mapping_is_stored_with_a_warning(
    stack: FakeStack,
) -> None:
    svc, _ = _service(stack)
    sid = stack.models().start(APIS, "Order").session_id
    # the good draft maps total <- orders[].total and number <- number on test-catalog-api
    total = svc.report(
        sid, API, "total", "wrong", "total is the order's own total", "orders[].total", GOOD
    )["id"]
    number = svc.report(sid, API, "Number", "wrong", "number is not available", "number", ABSENT)[
        "id"
    ]
    for rid in (total, number):
        svc.act(rid, "accept", "checked")
    fresh = _sessions(stack, svc)
    new = fresh.start(APIS, "Order").session_id
    result = fresh.submit(new, json.loads(DRAFT.read_text()))  # accepted: warnings only
    found = {
        (w.field, w.api): w.message
        for w in result.snapshot.warnings
        if w.code == "DIFFERS_FROM_VERIFIED"
    }
    assert set(found) == {("total", API), ("number", API)}
    assert found[("total", API)].startswith("differs from verified mapping vm-")
    assert f"(user report {total}): total (the draft maps orders[].total)" in found[("total", API)]
    assert "not available on test-catalog-api" in found[("number", API)]
    # the same mapping as the verified one: no warning
    draft = json.loads(DRAFT.read_text())
    field = next(f for f in draft["fields"] if f["name"] == "total")
    field["sources"][API]["paths"] = [{"path": "total", "type": "string"}]
    field["sources"][API]["evidence"] = GOOD["evidence"]
    warned = fresh.check(new, draft)
    assert [(w.field, w.api) for w in warned if w.code == "DIFFERS_FROM_VERIFIED"] == [
        ("number", API)
    ]


def test_another_field_mapping_a_verified_path_is_warned(stack: FakeStack) -> None:
    svc, _ = _service(stack)
    sid = stack.models().start(APIS, "Order").session_id
    total = svc.report(sid, API, "total", "wrong", "total is the order's own total", None, GOOD)[
        "id"
    ]
    number = svc.report(
        sid, API, "trackingCode", "wrong", "number is no tracking code", None, ABSENT
    )["id"]
    for rid in (total, number):
        svc.act(rid, "accept", "checked")
    fresh = _sessions(stack, svc)
    new = fresh.start(APIS, "Order").session_id
    draft = json.loads(DRAFT.read_text())
    fields = {f["name"]: f for f in draft["fields"]}
    fields["total"]["name"] = "grandAmount"  # another name, mapping the verified path
    fields["total"]["sources"][API]["paths"] = [{"path": "total", "type": "string"}]
    fields["total"]["sources"][API]["evidence"] = GOOD["evidence"]
    fields["number"]["name"] = "trackingCode"[::-1]  # another field mapping the notFrom path
    warned = {(w.field, w.api): w.message for w in fresh.check(new, draft)
              if w.code == "DIFFERS_FROM_VERIFIED"}  # fmt: skip
    assert warned[("grandAmount", API)] == (
        f"total is verified for `total` (verified mapping {svc.get(total)['verified']['id']} "
        f"(user report {total}))"
    )
    assert warned[("edoCgnikcart", API)].startswith(
        "number is verified as not being `trackingCode`"
    )
    # the verified field itself is now unmapped on that API: no draft field named "total"
    assert set(warned) == {("grandAmount", API), ("edoCgnikcart", API)}
