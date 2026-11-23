# ruff: noqa: E501
"""A full-URL call on a host that does not serve the endpoint (meta-ig-ai-graph: graph, ads-api
and mcp hosts), and which server each endpoint is on."""

from plume.domain.knowledge.call_check import environments_of, host_problem
from plume.domain.knowledge.document import Document, DocumentKind
from plume.infrastructure.sources.stream_package import _with_endpoint_servers

GUIDE = """# Meta environments and base URLs
- production: https://graph.facebook.com/v27.0 (default)
  - api_2: https://ads-api.facebook.com
  - api_3: https://mcp.facebook.com
  - auth: https://www.facebook.com/dialog/oauth
- europe: https://graph-eu.facebook.com/v27.0
"""


def test_a_host_of_another_server_is_not_this_endpoint() -> None:
    envs = environments_of(GUIDE)
    assert [e.name for e in envs] == ["production", "europe"]
    assert envs[0].url_of("api_2") == "https://ads-api.facebook.com"
    assert envs[1].url_of("api_2") == "https://graph-eu.facebook.com/v27.0"  # base stands in
    kind, why = host_problem("https://mcp.facebook.com/123/copies", None, envs) or ("", "")
    assert kind == "other_server"
    assert why.startswith("mcp.facebook.com is the api_3 server; this endpoint is on the base URL")
    assert host_problem("https://ads-api.facebook.com/ads", "api_3", envs)[0] == "other_server"  # type: ignore[index]
    assert host_problem("https://graph.facebook.com/v27.0/act_1/campaigns", None, envs) is None
    assert host_problem("https://graph-eu.facebook.com/v27.0/x", None, envs) is None  # region
    assert host_problem("/act_1/campaigns", None, envs) is None  # a relative path
    assert host_problem("https://example.com/x", None, envs)[0] == "unknown_host"  # type: ignore[index]


def test_a_templated_host_is_not_checked() -> None:
    envs = environments_of("- production: https://{{app_env.vars.host}}/admin (default)\n")
    assert host_problem("https://my-shop.example/admin/orders.json", None, envs) is None


def _endpoint(key: str) -> Document:
    return Document(doc_id=f"endpoint:GET~/{key}", kind=DocumentKind.ENDPOINT, title=key, text="t",
                    raw={"url": f"{{{{app_env.servers.{key}}}}}/{key}"})  # fmt: skip


def test_endpoints_say_their_server_when_there_are_several() -> None:
    app_json = {"environments": [{"isDefault": True, "baseUrl": "https://graph.facebook.com",
                                  "servers": {"api": "https://graph.facebook.com",
                                              "api_2": "https://ads-api.facebook.com",
                                              "auth": "https://www.facebook.com/oauth"}}]}  # fmt: skip
    app = Document(doc_id="app:meta", kind=DocumentKind.APP, title="a", text="t", raw={"app": {}})
    docs = _with_endpoint_servers([app, _endpoint("api"), _endpoint("api_2")], app_json)
    assert docs[1].text.endswith("Server: api (https://graph.facebook.com)")
    assert docs[2].text.endswith("Server: api_2 (https://ads-api.facebook.com)")
    assert (docs[0].raw or {})["server_endpoints"] == {"api": 1, "api_2": 1}
    single = {"environments": [{"baseUrl": "https://a.example", "servers": {
        "api": "https://a.example", "auth": "https://login.example"}}]}  # fmt: skip
    one = _with_endpoint_servers([app, _endpoint("api")], single)
    assert one[1].text == "t"  # one API server (auth is OAuth): nothing to say
    assert (one[0].raw or {})["server_endpoints"] == {"api": 1}
