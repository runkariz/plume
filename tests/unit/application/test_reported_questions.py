"""Reported questions: the service (dedupe, notes, limits, safety, retention, status)."""

from datetime import timedelta
from pathlib import Path

import pytest

from plume.application.reports.service import (
    ReportedQuestions,
    ReportRefusedError,
    ReportsDisabledError,
)
from tests.fakes.knowledge import FakeClock, WordEmbedder
from tests.fakes.reports import InMemoryReports
from tests.fakes.stack import FakeStack

API = "test-catalog-api"


@pytest.fixture
def stack(packages: Path) -> FakeStack:
    s = FakeStack(embedder=WordEmbedder())
    s.load(str(packages / "test-catalog"))
    return s


def _service(
    stack: FakeStack, **kw: object
) -> tuple[ReportedQuestions, InMemoryReports, FakeClock]:
    repo, clock = InMemoryReports(), FakeClock(step=timedelta(seconds=1))
    svc = ReportedQuestions(repo, stack.embedder, stack.resolver(), clock, enabled=True,
                            salt=b"k", **kw)  # type: ignore[arg-type]  # fmt: skip
    return svc, repo, clock


def test_report_then_find_then_a_duplicate_becomes_a_note(stack: FakeStack) -> None:
    svc, repo, _ = _service(stack)
    assert svc.find(API, "how do I refresh an expired access token")["similar"] == []
    first = svc.report(API, "How do I refresh an expired access token?", "search_docs refresh",
                       "the refresh endpoint", "claude-code", "sess-1")  # fmt: skip
    assert first["merged"] is False
    rid = first["id"]
    found = svc.find(API, "refresh an expired access token")["similar"]
    assert found[0]["id"] == rid
    assert found[0]["status"] == "open"
    # the same words: a note on it, and it says so
    again = svc.report(API, "how do I refresh an expired access token", None, None, None, "s2")
    assert again["merged"] is True
    assert again["id"] == rid
    assert "already reported" in again["message"]
    # the same words in another order (the embeddings agree): merged too
    reordered = svc.report(API, "refresh an expired access token: how do I?", None, None)
    assert reordered["id"] == rid
    report = repo.get(rid)
    assert report is not None
    assert (report.report_count, report.note_count) == (3, 2)
    assert [n.kind for n in repo.notes(rid)] == ["duplicate", "duplicate"]


def test_add_to_report_raises_the_count(stack: FakeStack) -> None:
    svc, repo, _ = _service(stack)
    rid = svc.report(API, "where is the bulk price update documented", None, None)["id"]
    out = svc.add_note(rid, "also needed this for the CSV import", "cursor", "s9")
    assert out["report"]["report_count"] == 2
    assert repo.notes(rid)[0].text == "also needed this for the CSV import"
    with pytest.raises(LookupError):
        svc.add_note("rq-missing", "x")


def test_limits_length_and_unsafe_text_are_refused_politely(stack: FakeStack) -> None:
    svc, _, _ = _service(stack, per_hour=3)
    for i in range(3):
        svc.report(API, f"question number {['one', 'two', 'three'][i]} about paging", None, None,
                   None, "busy")  # fmt: skip
    with pytest.raises(ReportRefusedError, match="last hour"):
        svc.report(API, "a fourth question about rate limits", None, None, None, "busy")
    svc.report(API, "another session asks about rate limits", None, None, None, "calm")
    with pytest.raises(ReportRefusedError, match="1000 characters"):
        svc.report(API, "x" * 1001, None, None)
    with pytest.raises(ReportRefusedError, match="general terms"):
        svc.report(API, "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2ln 123456789012 a@b.co",
                   None, None)  # fmt: skip
    # redacted but still general: stored
    stored = svc.report(API, "my token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2ln expired: "
                        "how do I renew it", None, None, None, "calm")  # fmt: skip
    assert "eyJ" not in stored["report"]["question"]
    assert "how do I renew it" in stored["report"]["question"]


def test_the_owner_rules_keep_error_codes_and_the_rpc_method(stack: FakeStack) -> None:
    svc, repo, _ = _service(stack)
    tried = "check_call POST /sync method=aliexpress.solution.order.get"
    rid = svc.report(API, "what does error code 36009003 mean for coupons", tried, None)["id"]
    r = repo.get(rid)
    assert r is not None
    assert "36009003" in r.question
    assert "method=aliexpress.solution.order.get" in (r.what_was_tried or "")


def test_retention_purges_untouched_open_reports_and_keeps_triaged_ones(stack: FakeStack) -> None:
    svc, repo, clock = _service(stack, retention_days=90)
    old = svc.report(API, "how are list results paged", None, None)["id"]
    kept = svc.report(API, "what is the webhook signature header", None, None)["id"]
    svc.set_status(kept, "package-gap", "the package does not document webhook signing")
    clock._now += timedelta(days=91)
    assert svc.purge() == 1
    assert repo.get(old) is None
    assert repo.get(kept) is not None


def test_status_reasons_shown_to_readers_only_when_closed(stack: FakeStack) -> None:
    svc, _, _ = _service(stack)
    rid = svc.report(API, "how do I list archived orders", None, None)["id"]
    svc.set_status(rid, "out-of-scope", "archived orders are not in this API")
    hit = svc.find(API, "list archived orders")["similar"][0]
    assert hit["reason"] == "archived orders are not in this API"
    with pytest.raises(ReportRefusedError, match="status must be one of"):
        svc.set_status(rid, "maybe")


def test_off_means_off(stack: FakeStack) -> None:
    svc, _, _ = _service(stack)
    off = ReportedQuestions(InMemoryReports(), stack.embedder, stack.resolver(), FakeClock(),
                            enabled=False, salt=b"k")  # fmt: skip
    with pytest.raises(ReportsDisabledError):
        off.report(API, "anything", None, None)
    assert svc.enabled
