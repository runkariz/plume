"""Graph-style APIs share a route shape between endpoints of different parent nodes (Meta
Marketing GET /{campaign_id}/copies vs GET /{ad_id}/copies): check_call checks the params
against every equal candidate. One that documents them all wins (the others are alternatives);
params split across candidates make the call ambiguous; a param a candidate documents is never
not documented."""

import json
import shutil
from typing import Any

import pytest

from plume.domain.knowledge.call_check import route_shape
from plume.interfaces.payloads import check_call_payload
from tests.fakes.stack import FakeStack

API = "{{app_env.servers.api}}"
S, B = {"type": "string"}, {"type": "boolean"}
ENDPOINTS = {  # folder: (method, path, {query param: schema})
    "get-campaign-copies": ("GET", "/{campaign_id}/copies",
                            {"is_completed": B, "date_preset": S}),
    "get-ad-copies": ("GET", "/{ad_id}/copies",
                      {"date_preset": S, "effective_status": S}),
    "post-ad-adlabels": ("POST", "/{ad_id}/adlabels",
                         {"adlabels": {"type": "string"},
                          "execution_options": {"type": "string", "enum": ["validate_only"]}}),
    "post-creative-adlabels": ("POST", "/{ad_creative_id}/adlabels",
                               {"adlabels": {"type": "string"}}),
}  # fmt: skip
DEPRECATED = {"post-creative-adlabels"}  # sorts first by id, so the tie-break must override it


@pytest.fixture(scope="module")
def stack(tmp_path_factory: pytest.TempPathFactory) -> FakeStack:
    from tests.conftest import PACKAGES  # noqa: PLC0415

    dst = tmp_path_factory.mktemp("graph") / "shopify"
    shutil.copytree(PACKAGES / "shopify-mini", dst)
    for folder, (method, path, params) in ENDPOINTS.items():
        d = dst / "connector" / "endpoints" / folder
        d.mkdir()
        (d / "params.schema.json").write_text(json.dumps({"type": "object", "properties": params}))
        (d / "request.json").write_text(json.dumps({
            "endpointId": folder, "name": folder, "method": method, "url": API + path,
            "resource": "Thing", "bodyType": "NONE", "paramsContractRef": "params.schema.json",
            "responses": [], "isDeprecated": folder in DEPRECATED,
        }))  # fmt: skip
    s = FakeStack()
    s.load(str(dst))
    return s


def _check(stack: FakeStack, method: str, path: str, params: list[str]) -> dict[str, Any]:
    return check_call_payload(stack.check_call().execute("shopify", method, path, params))


def test_route_shape_blanks_variable_names() -> None:
    assert route_shape("/{campaign_id}/copies") == route_shape("/{ad_id}/copies") == "{}/copies"
    assert route_shape("/act_{id}/ads") == "act_{}/ads"


def test_the_candidate_that_documents_every_param_wins(stack: FakeStack) -> None:
    r = _check(stack, "GET", "/123/copies", ["is_completed"])
    assert r["verdict"] == "documented"
    assert r["matched"]["doc_id"] == "endpoint:GET~/{campaign_id}/copies"
    assert r["alternatives"] == ["endpoint:GET~/{ad_id}/copies"]
    assert {c["doc_id"]: c["documents"] for c in r["candidates"]} == {
        "endpoint:GET~/{campaign_id}/copies": ["is_completed"],
        "endpoint:GET~/{ad_id}/copies": [],
    }


def test_params_split_across_candidates_are_ambiguous(stack: FakeStack) -> None:
    r = _check(stack, "GET", "/123/copies", ["is_completed", "effective_status"])
    assert r["verdict"] == "ambiguous"
    assert r["matched"] is None
    assert sorted(r["alternatives"]) == [
        "endpoint:GET~/{ad_id}/copies", "endpoint:GET~/{campaign_id}/copies"]  # fmt: skip
    assert all(p["found"] for p in r["params"])
    assert "none documents all these params" in r["note"]
    assert {c["doc_id"]: c["documents"] for c in r["candidates"]} == {
        "endpoint:GET~/{campaign_id}/copies": ["is_completed"],
        "endpoint:GET~/{ad_id}/copies": ["effective_status"],
    }


def test_a_param_a_sibling_documents_is_never_not_documented(stack: FakeStack) -> None:
    r = _check(stack, "GET", "/123/copies", ["is_completed", "effective_status", "nope"])
    assert r["verdict"] == "not_documented"  # nope is documented nowhere
    found = {p["name"]: p["found"] for p in r["params"]}
    assert found == {"is_completed": True, "effective_status": True, "nope": False}
    sibling = next(p for p in r["params"] if p["note"])
    assert "not on the matched operation" in sibling["note"]


def test_a_single_value_enum_does_not_pick_across_parents(stack: FakeStack) -> None:
    """execution_options: [validate_only] on one parent is a constraint, not an RPC name."""
    r = _check(stack, "POST", "/123/adlabels", ["adlabels", "execution_options"])
    assert r["verdict"] == "documented"
    assert r["matched"]["doc_id"] == "endpoint:POST~/{ad_id}/adlabels"
    assert r["pick"] is None


def test_a_non_deprecated_candidate_wins_a_tie_and_deprecated_ones_are_marked(
    stack: FakeStack,
) -> None:
    """Both document adlabels: the non-deprecated one is matched, though the deprecated one
    sorts first by id."""
    r = _check(stack, "POST", "/123/adlabels", ["adlabels"])
    assert r["matched"]["doc_id"] == "endpoint:POST~/{ad_id}/adlabels"
    assert {c["doc_id"]: c["deprecated"] for c in r["candidates"]} == {
        "endpoint:POST~/{ad_creative_id}/adlabels": True,
        "endpoint:POST~/{ad_id}/adlabels": False,
    }
    bare = _check(stack, "POST", "/123/adlabels", [])  # no params: still the non-deprecated one
    assert bare["matched"]["doc_id"] == "endpoint:POST~/{ad_id}/adlabels"
