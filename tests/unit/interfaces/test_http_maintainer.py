import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plume.application.knowledge.diff_builds import DiffBuilds
from plume.application.knowledge.list_builds import ListBuilds
from plume.infrastructure.sources.gold_file import JsonGoldSource
from plume.interfaces.http.app import HttpDependencies, create_app
from tests.fakes.knowledge import WordEmbedder
from tests.fakes.stack import FakeStack
from tests.unit.infrastructure.test_dumps_and_storage import zip_dir

TOKEN = "pl_test_token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
GOLD = Path(__file__).resolve().parents[2] / "fixtures" / "gold"


def _client(
    stack: FakeStack, tokens: tuple[str, ...] = (TOKEN,), generate: bool = False
) -> TestClient:
    return TestClient(
        create_app(
            HttpDependencies(
                overviews=stack.overviews,
                browse=stack.browse,
                search=stack.search,
                get_document=stack.get_document,
                find_fact=stack.find_fact,
                check_call=stack.check_call,
                list_builds=lambda: ListBuilds(stack.builds, stack.tags),
                diff_builds=lambda: DiffBuilds(stack.builds),
                resolver=stack.resolver,
                rate_limit_per_minute=0,
                maintainer=stack.maintainer,
                maintainer_tokens=tokens,
                models=stack.models if generate else None,
                suggest=stack.suggest if generate else None,
                generate_models=stack.generate if generate else None,
            )
        )
    )


@pytest.fixture
def stack(tmp_path: Path) -> FakeStack:
    return FakeStack(embedder=WordEmbedder(), gold=JsonGoldSource([GOLD]), data_dir=tmp_path)


def _sse(body: str) -> list[dict[str, str]]:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "data" in fields:
            events.append(fields)
    return events


def test_auth(stack: FakeStack) -> None:
    client = _client(stack)
    assert client.get("/v1/maintainer/me").status_code == 401
    r = client.get("/v1/maintainer/me", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401
    assert r.json()["error"] == "unauthorized"
    assert r.headers["www-authenticate"] == "Bearer"
    me = client.get("/v1/maintainer/me", headers=AUTH).json()
    assert me == {"name": "maintainer", "generation": False}  # no generation configured


def test_me_says_whether_server_generation_works(stack: FakeStack) -> None:
    on = _client(stack, generate=True).get("/v1/maintainer/me", headers=AUTH).json()
    assert on["generation"] is True
    stack.writer = type(stack.writer)(available=False)  # no model key
    off = _client(stack, generate=True).get("/v1/maintainer/me", headers=AUTH).json()
    assert off["generation"] is False
    off = _client(stack, tokens=())
    assert off.get("/v1/maintainer/me", headers=AUTH).status_code == 503


def test_wizard_over_http(stack: FakeStack, packages: Path) -> None:
    client = _client(stack)
    data = zip_dir(packages / "test-catalog")
    r = client.post(
        "/v1/packages", headers=AUTH, files={"file": ("cat.zip", data, "application/zip")}
    )
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "uploaded"
    assert job["package"]["filename"] == "cat.zip"
    jid = job["id"]

    r = client.post(
        f"/v1/jobs/{jid}/review",
        headers=AUTH,
        json={"apiId": "test-catalog-api", "displayName": "Catalog", "tag": "latest"},
    )
    assert r.json()["status"] == "reviewed"
    assert r.json()["plan"]["dimensions"] == 768
    assert client.post(f"/v1/jobs/{jid}/build", headers=AUTH).status_code == 200

    stream = client.get(f"/v1/jobs/{jid}/events", headers=AUTH)
    assert stream.headers["content-type"].startswith("text/event-stream")
    events = _sse(stream.text)
    assert events[-1]["event"] == "done"
    assert json.loads(events[-1]["data"])["status"] == "staged"
    ids = [int(e["id"]) for e in events]
    assert ids == sorted(ids)
    assert all(json.loads(e["data"])["id"] == e["id"] for e in events)

    resumed = _sse(
        client.get(
            f"/v1/jobs/{jid}/events", headers={**AUTH, "Last-Event-ID": events[2]["id"]}
        ).text
    )
    assert [e["id"] for e in resumed] == [e["id"] for e in events[3:]]

    assert client.get(f"/v1/jobs/{jid}", headers=AUTH).json()["eval"]["gate"]["passed"] is True
    pub = client.post(f"/v1/jobs/{jid}/publish", headers=AUTH)
    assert pub.json()["status"] == "published"
    assert client.get("/v1/apis/test-catalog-api").json()["tag"] == "latest"
    dump = client.get(f"/v1/jobs/{jid}/dump", headers=AUTH)
    assert dump.headers["content-type"] == "application/gzip"
    assert "attachment" in dump.headers["content-disposition"]
    assert client.post(f"/v1/jobs/{jid}/publish", headers=AUTH).status_code == 409


def test_upload_errors(stack: FakeStack) -> None:
    client = _client(stack)
    r = client.post("/v1/packages", headers=AUTH, files={"file": ("x.tar", b"x", "x/y")})
    assert r.status_code == 415
    assert r.json()["detail"] == "Only .zip packages are accepted"
    r = client.post("/v1/packages", headers=AUTH, files={"file": ("x.zip", b"nope", "x/y")})
    assert r.status_code == 400
    assert client.get("/v1/jobs/job-nope", headers=AUTH).status_code == 404
    assert client.get("/v1/jobs/job-nope/events", headers=AUTH).status_code == 404


def test_cors_allows_maintainer_headers(stack: FakeStack) -> None:
    r = _client(stack).options(
        "/v1/jobs/x/events",
        headers={
            "Origin": "http://127.0.0.1:18473",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,last-event-id",
        },
    )
    assert r.status_code == 200
    allowed = r.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed
    assert "last-event-id" in allowed


def test_cors_allows_put_for_the_display_name(stack: FakeStack) -> None:
    r = _client(stack).options(
        "/v1/apis/x/display",
        headers={"Origin": "http://127.0.0.1:18473", "Access-Control-Request-Method": "PUT",
                 "Access-Control-Request-Headers": "authorization,content-type"},
    )  # fmt: skip
    assert r.status_code == 200
    assert "PUT" in r.headers["access-control-allow-methods"]


def test_quality_after_publish(stack: FakeStack, packages: Path) -> None:
    client = _client(stack)
    data = zip_dir(packages / "test-catalog")
    jid = client.post(
        "/v1/packages", headers=AUTH, files={"file": ("c.zip", data, "application/zip")}
    ).json()["id"]
    client.post(
        f"/v1/jobs/{jid}/review", headers=AUTH, json={"apiId": "test-catalog-api", "tag": "latest"}
    )
    client.post(f"/v1/jobs/{jid}/build", headers=AUTH)
    client.post(f"/v1/jobs/{jid}/publish", headers=AUTH)
    item = client.get("/v1/apis").json()["items"][0]
    assert item["status"] == {"kind": "ready", "recallAt5": 1.0}
    q = client.get("/v1/apis/test-catalog-api").json()["quality"]
    assert q["goldQuestions"] == 8
    assert q["gatePassed"] is True
    assert q["inventedEndpoints"] is None
