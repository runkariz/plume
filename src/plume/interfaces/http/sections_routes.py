"""Package sections as stored: auth schemes, triggers (events), the package's own icon."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from plume.application.reader.sections import (
    PackageSections,
    endpoint_ids_in,
    scheme_view,
    trigger_view,
)
from plume.interfaces.http import schemas as s

NOT_IN_PACKAGE = "not in this package"


def _scheme_summary(v: dict[str, Any]) -> s.AuthSchemeSummary:
    return s.AuthSchemeSummary(
        id=str(v["id"]),
        doc_id=v["doc_id"],
        name=v["name"],
        type=v["type"],
        grant_type=v["grant_type"],
        header_name=v["header_name"],
        query_param=v["query_param"],
        scopes=len(v["scopes"]),
        variables=len(v["variables"]),
    )


def _trigger_summary(v: dict[str, Any]) -> s.TriggerSummary:
    return s.TriggerSummary(
        key=v["key"],
        doc_id=v["doc_id"],
        title=v["title"],
        description=v["description"],
        resource=v["resource"],
        delivery=v["delivery"],
        sync_endpoint_id=v["sync_endpoint_id"],
    )


def sections_router(sections: Callable[[], PackageSections]) -> APIRouter:
    router = APIRouter(tags=["reader"])
    errors: dict[int | str, dict[str, Any]] = {404: {"model": s.ErrorBody}}
    version_q = Annotated[str | None, Query(description="Tag or build id; default latest")]

    @router.get("/v1/apis/{api}/auth", response_model=s.AuthList, responses=errors)
    def auth(api: str, version: version_q = None) -> s.AuthList:
        """Auth schemes as the package states them (empty + note when it has none)."""
        ref, docs = sections().auth_schemes(api, version)
        views = [scheme_view(d) for d in docs]
        return s.AuthList(
            api=ref.api,
            build=ref.build,
            present=bool(views),
            note=None if views else NOT_IN_PACKAGE,
            schemes=[_scheme_summary(v) for v in views],
        )

    @router.get(
        "/v1/apis/{api}/auth/{scheme_id}", response_model=s.AuthSchemeDetail, responses=errors
    )
    def auth_scheme(api: str, scheme_id: str, version: version_q = None) -> s.AuthSchemeDetail:
        """One auth scheme: its JSON and variables schema verbatim, plus fields read from them."""
        ref, doc = sections().auth_scheme(api, scheme_id, version)
        v = scheme_view(doc)
        return s.AuthSchemeDetail(
            api=ref.api,
            build=ref.build,
            id=str(v["id"]),
            doc_id=v["doc_id"],
            name=v["name"],
            type=v["type"],
            grant_type=v["grant_type"],
            header_name=v["header_name"],
            query_param=v["query_param"],
            scopes=[s.AuthScope(**x) for x in v["scopes"]],
            variables=[s.AuthVariable(**x) for x in v["variables"]],
            setup_steps=v["setup_steps"],
            token_lifetime=v["token_lifetime"],
            test_url=v["test_url"],
            scheme=v["scheme"],
            variables_schema=v["variables_schema"],
            file=v["file"],
        )

    @router.get("/v1/apis/{api}/environments", response_model=s.EnvironmentsOut, responses=errors)
    def environments(api: str, version: version_q = None) -> s.EnvironmentsOut:
        """Environments (servers, variables such as the shop host) and API versioning, as the
        package states them."""
        ref, env = sections().environments(api, version)
        envs = env["environments"] or []
        return s.EnvironmentsOut(
            api=ref.api,
            build=ref.build,
            present=bool(envs),
            note=None if envs else NOT_IN_PACKAGE,
            environments=[e for e in envs if isinstance(e, dict)],
            versioning=env["versioning"] if isinstance(env["versioning"], dict) else None,
            base_urls=env["base_urls"] if isinstance(env["base_urls"], list) else None,
            variables_schema=env["variables_schema"],
        )

    @router.get("/v1/apis/{api}/triggers", response_model=s.TriggerList, responses=errors)
    def triggers(
        api: str,
        version: version_q = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 200,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> s.TriggerList:
        """Trigger events (webhook topics) as the package lists them; present=false + note when
        the package has none."""
        ref, docs = sections().triggers(api, version)
        views = [trigger_view(d) for d in docs]
        hooks = sections().webhooks(api, version)
        refs = sections().endpoint_refs(
            api, endpoint_ids_in(hooks) + endpoint_ids_in([v["event"] for v in views]), version
        )
        return s.TriggerList(
            api=ref.api,
            build=ref.build,
            present=bool(views or hooks),
            note=None if views or hooks else NOT_IN_PACKAGE,
            total=len(views),
            items=[_trigger_summary(v) for v in views[offset : offset + limit]],
            webhooks=hooks,
            endpoint_refs={
                k: s.EndpointRef(doc_id=v["doc_id"], method=v["method"], path=v["path"])
                if v
                else None
                for k, v in refs.items()
            },
        )

    @router.get("/v1/apis/{api}/mcp", response_model=s.McpOut, responses=errors)
    def mcp(api: str, version: version_q = None) -> s.McpOut:
        """The vendor's MCP server(s) and tools, when the package has a connector/mcp/ section."""
        ref, section = sections().mcp(api, version)
        servers = section.get("servers", []) if section else []
        return s.McpOut(
            api=ref.api,
            build=ref.build,
            present=bool(servers),
            note=None if servers else NOT_IN_PACKAGE,
            servers=servers,
        )

    @router.get(
        "/v1/apis/{api}/triggers/{key:path}", response_model=s.TriggerDetail, responses=errors
    )
    def trigger(api: str, key: str, version: version_q = None) -> s.TriggerDetail:
        """One trigger by its key (e.g. app/scopes_update) or document id; the event JSON
        verbatim."""
        ref, doc = sections().trigger(api, key, version)
        v = trigger_view(doc)
        return s.TriggerDetail(
            **_trigger_summary(v).model_dump(),
            api=ref.api,
            build=ref.build,
            source_url=v["source_url"],
            event=v["event"],
        )

    @router.get(
        "/v1/apis/{api}/icon",
        responses={**errors, 200: {"content": {"image/png": {}, "image/svg+xml": {}}}},
        response_class=Response,
    )
    def icon(api: str, request: Request, version: version_q = None) -> Response:
        """The package's own icon, stored with the build (no third-party fetch)."""
        _, asset = sections().icon(api, version)
        if asset is None:
            return Response(
                content=b'{"error":"not_found","message":"no icon in this package",'
                b'"detail":"no icon in this package"}',
                status_code=404,
                media_type="application/json",
            )
        etag = f'"{asset.sha256[:32]}"'
        headers = {
            "ETag": etag,
            "Cache-Control": "public, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            # A public, static image loaded by <img> (a no-cors request) from the web UI's own
            # origin: browsers treat another port as another site, so same-site would block it.
            "Cross-Origin-Resource-Policy": "cross-origin",
        }
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(content=asset.data, media_type=asset.content_type, headers=headers)

    return router
