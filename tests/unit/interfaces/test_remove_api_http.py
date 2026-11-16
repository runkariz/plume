"""DELETE /v1/apis/{api}: token, typed confirm, 409 api_in_use with pinnedBy, force."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.interfaces.http.app import HttpDependencies, create_app
from tests.fakes.stack import FakeStack

API = "test-catalog-api"
TOKEN = "pl_remove_test"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
DRAFTS = Path(__file__).resolve().parents[2] / "fixtures" / "drafts"


def test_remove_api_route(packages: Path) -> None:
    s = FakeStack()
    s.load(str(packages / "test-catalog"))
    s.load(str(packages / "second-catalog"))
    draft = json.loads((DRAFTS / "catalog-order-good.json").read_text())
    session = s.models().start([API, "second-catalog-api"], "Order")
    mid = s.models().submit(session.session_id, draft, maintainer=True).snapshot.snapshot_id
    client = TestClient(
        create_app(
            HttpDependencies(
                overviews=s.overviews, browse=s.browse, search=s.search,
                get_document=s.get_document, find_fact=s.find_fact, check_call=s.check_call,
                list_builds=lambda: ListBuilds(s.builds, s.tags),
                diff_builds=lambda: DiffBuilds(s.builds), resolver=s.resolver,
                rate_limit_per_minute=0, maintainer_tokens=(TOKEN,), api_display=s.api_display,
                remove_api=s.remove_api, models=s.models, model_impact=s.model_impact,
                suggest=s.suggest,
                public_changes=s.public_changes,
            )
        )
    )  # fmt: skip
    url = f"/v1/apis/{API}"
    assert client.request("DELETE", url, json={"confirm": API}).status_code == 401
    bad = client.request("DELETE", url, json={"confirm": "x"}, headers=AUTH)
    assert (bad.status_code, bad.json()["error"]) == (409, "invalid_input")
    check = client.get(f"{url}/removal", headers=AUTH).json()
    assert [p["id"] for p in check["pinnedBy"]] == [mid]
    refused = client.request("DELETE", url, json={"confirm": API}, headers=AUTH)
    assert refused.status_code == 409
    assert refused.json()["error"] == "api_in_use"
    assert refused.json()["pinnedBy"][0]["id"] == mid
    done = client.request("DELETE", url, json={"confirm": API, "force": True}, headers=AUTH)
    assert done.status_code == 200
    assert done.json()["removed"]["api"] == 1
    assert client.get(url).status_code == 404
    assert [a["id"] for a in client.get("/v1/apis").json()["items"]] == ["second-catalog-api"]
    model = client.get(f"/v1/models/{mid}", headers=AUTH)  # its pinned API is gone
    assert model.status_code == 200, model.text
    assert model.json()["impact"]["status"] == "unknown"
