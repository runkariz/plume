# ruff: noqa: E501
"""A knowledge unit whose sample merely calls an endpoint (unit-links linkBasis "sample-call")
is not that endpoint's documentation: no rules, no documentation page, listed apart (Meta's
reminder-ads guides on POST /act_{AD_ACCOUNT_ID}/campaigns)."""

from plume.domain.knowledge.document import Document, DocumentKind
from plume.infrastructure.sources.knowledge_export import (
    ExportPage,
    KnowledgeExport,
    without_sample_calls,
)
from plume.infrastructure.sources.stream_package import _link_documents

EP = "post-act-ad-account-id-campaigns"


def _page(*items: str) -> ExportPage:
    return ExportPage(file="p.md", source_url="https://x/reminder-ads", title="Reminder ads",
                      intro="", items=[(i, i) for i in items],
                      sections={EP: ("#create", "text")})  # fmt: skip


def test_an_endpoint_a_page_only_samples_leaves_the_page() -> None:
    page = _page("knowledge:workflow-reminder", "knowledge:validation-reminder", EP)
    links: dict[str, tuple[tuple[str, ...], str]] = {"workflow-reminder": ((EP,), "sample-call"),
             "validation-reminder": ((EP,), "sample-call")}  # fmt: skip
    export = without_sample_calls(
        KnowledgeExport(complete=True, pages=[page], rules=[], gold_path=None), links
    )
    assert [i for i, _ in export.pages[0].items] == ["knowledge:workflow-reminder",
                                                     "knowledge:validation-reminder"]  # fmt: skip
    assert export.pages[0].sections == {}
    assert export.pages[0].sample_calls == [EP]


def test_any_other_link_keeps_the_endpoint_on_its_page() -> None:
    page = _page("knowledge:workflow-reminder", "knowledge:campaign-rules", EP)
    links: dict[str, tuple[tuple[str, ...], str]] = {
        "workflow-reminder": ((EP,), "sample-call"),
        "campaign-rules": ((EP,), "page"),
    }
    export = without_sample_calls(
        KnowledgeExport(complete=True, pages=[page], rules=[], gold_path=None), links
    )
    assert EP in [i for i, _ in export.pages[0].items]
    unlinked = without_sample_calls(
        KnowledgeExport(complete=True, pages=[_page("knowledge:a", EP)], rules=[], gold_path=None),
        {},
    )
    assert EP in [i for i, _ in unlinked.pages[0].items]  # no unit links: unchanged


def test_sample_call_guides_are_listed_apart() -> None:
    endpoint = Document(doc_id="endpoint:POST~/act_{AD_ACCOUNT_ID}/campaigns",
                        kind=DocumentKind.ENDPOINT, title="Create campaign", text="t",
                        method="POST", path="/act_{AD_ACCOUNT_ID}/campaigns", source_id=EP)  # fmt: skip

    def unit(name: str, basis: str) -> Document:
        return Document(doc_id=f"guide:{name}", kind=DocumentKind.GUIDE, title=name, text="t",
                        source_id=name, raw={"endpointIds": [EP], "linkBasis": {EP: basis}})  # fmt: skip

    docs = _link_documents([endpoint, unit("reminder", "sample-call"), unit("rules", "page")],
                           [], ())  # fmt: skip
    raw = docs[0].raw or {}
    assert raw["x-plume-guides"] == ["guide:rules"]
    assert raw["x-plume-sample-guides"] == ["guide:reminder"]
    assert (docs[1].raw or {})["endpoints"] == [endpoint.doc_id]  # the unit's own link stays
