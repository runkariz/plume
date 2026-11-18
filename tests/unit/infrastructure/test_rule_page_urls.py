"""knowledge-export rules find their page by sourceUrl: exact, then loosely (percent-encoded
= decoded, trailing slash, host case), then without a query when only one page has the
path. A leftover warning names examples."""

from plume.domain.knowledge.document import Document, DocumentKind
from plume.infrastructure.sources.knowledge_export import ExportPage, KnowledgeExport, Rule
from plume.infrastructure.sources.stream_package import _apply_export, _rule_pages, url_key

LAZADA_DOC = "https://open.lazada.com/apps/doc/doc?nodeId=30720&docId=120949"
TR = "https://developers.trendyol.com/docs/kategori-özellik-değerleri-listesi-v2"
TR_ENCODED = "https://developers.trendyol.com/docs/kategori-%C3%B6zellik-de%C4%9Ferleri-listesi-v2"


def _page(url: str) -> ExportPage:
    return ExportPage(file=url.rsplit("/", 1)[-1] + ".md", source_url=url, title="t", intro="x")


def _rule(rule_id: str, url: str | None) -> Rule:
    return Rule(rule_id, "resource", "rule", f"text {rule_id}", "quote", url, None, None, None)


PAGES = [
    _page("https://open.lazada.com/apps/doc/api?path=%2Fproducts%2Fget"),
    _page("https://open.lazada.com/apps/doc/api?path=%2Forders%2Fget"),
    _page(LAZADA_DOC),
    _page(TR),
    _page("https://Shop.Example.com/docs/a/"),
]


def test_url_key_decodes_and_keeps_the_query() -> None:
    assert url_key(TR_ENCODED) == url_key(TR)
    assert url_key("https://Shop.Example.com/docs/a/#x") == "https://shop.example.com/docs/a"
    assert url_key(LAZADA_DOC).endswith("?nodeId=30720&docId=120949")


def test_rules_find_their_page() -> None:
    rules = [
        _rule("exact", LAZADA_DOC),
        _rule("encoded", TR_ENCODED),
        _rule("slash", "https://shop.example.com/docs/a"),
        _rule("no-query", "https://open.lazada.com/apps/doc/doc"),  # one page has this path
        _rule("ambiguous", "https://open.lazada.com/apps/doc/api"),  # two pages: no guess
        _rule("other-query", "https://open.lazada.com/apps/doc/api?path=%2Fnope"),
        _rule("none", None),
    ]
    export = KnowledgeExport(complete=True, pages=PAGES, rules=rules, gold_path=None)
    found = {rules[i].rule_id: PAGES[p].source_url for i, p in _rule_pages(export, set()).items()}
    assert found == {
        "exact": LAZADA_DOC,
        "encoded": TR,
        "slash": "https://Shop.Example.com/docs/a/",
        "no-query": LAZADA_DOC,
    }
    assert _rule_pages(export, {"exact"}).keys() == {1, 2, 3}  # used rules are skipped


def test_leftover_warning_lists_examples() -> None:
    rules = [_rule(f"r{i}", f"https://nowhere.example/{i}") for i in range(5)]
    export = KnowledgeExport(complete=True, pages=[], rules=rules, gold_path=None)
    app = Document(doc_id="app:x", kind=DocumentKind.APP, title="X", text="x")
    warnings: list[str] = []
    _apply_export([app], export, warnings)
    assert warnings == [
        "knowledge-export: 5 rule(s) matched no endpoint or page (e.g. "
        "r0 https://nowhere.example/0; r1 https://nowhere.example/1; "
        "r2 https://nowhere.example/2; +2 more)"
    ]
