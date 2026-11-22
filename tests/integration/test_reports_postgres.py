"""PostgresReportRepo against the real schema (migration 0018)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text

from plume.domain.reports.report import Report, ReportNote, ReportStatus
from plume.infrastructure.db.alembic_migrator import AlembicMigrator
from plume.infrastructure.db.repos.report_repo import PostgresReportRepo

pytestmark = pytest.mark.integration
T0 = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)


@pytest.fixture
def repo(engine: Engine) -> Iterator[PostgresReportRepo]:
    AlembicMigrator(engine).upgrade_to_head()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM reported_questions"))
    yield PostgresReportRepo(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM reported_questions"))


def _report(rid: str, question: str, at: datetime, session: str | None = "s1") -> Report:
    return Report(report_id=rid, api="shopify", question=question, status=ReportStatus.OPEN,
                  created_at=at, updated_at=at, build_id="b-1", session_hash=session)  # fmt: skip


def test_add_find_note_label_and_purge(repo: PostgresReportRepo) -> None:
    repo.add(_report("rq-a", "how do I refresh a token", T0), "how do i refresh a token",
             [1.0, 0.0, 0.0], "m")  # fmt: skip
    repo.add(_report("rq-b", "what is the rate limit", T0), "what is the rate limit",
             [0.0, 1.0, 0.0], "m")  # fmt: skip
    near = repo.similar("shopify", [0.9, 0.1, 0.0], "m", 2)
    assert [r.report_id for r, _ in near] == ["rq-a", "rq-b"]
    assert near[0][1] > 0.9
    assert repo.similar("shopify", [1.0, 0.0, 0.0], "other-model", 2) == []
    assert repo.by_key("shopify", "what is the rate limit") is not None
    repo.add_note(ReportNote("rn-1", "rq-a", "also needed", T0 + timedelta(minutes=1),
                             session_hash="s1"))  # fmt: skip
    a = repo.get("rq-a")
    assert a is not None
    assert (a.report_count, a.note_count) == (2, 1)
    assert [n.text for n in repo.notes("rq-a")] == ["also needed"]
    assert repo.writes_since("s1", T0 - timedelta(minutes=5)) == 3
    assert repo.writes_since(None, T0 - timedelta(minutes=5)) == 0
    assert next(r.report_id for r in repo.list("shopify", None, None)) == "rq-a"
    assert repo.set_status("rq-b", ReportStatus.PACKAGE_GAP, "not documented", T0)
    assert repo.purge_open(T0 + timedelta(days=200)) == 1  # rq-a (open); rq-b is triaged
    assert repo.get("rq-a") is None
    assert repo.notes("rq-a") == []
    assert repo.get("rq-b") is not None


def test_consent_method_round_trips(repo: PostgresReportRepo) -> None:
    from dataclasses import replace  # noqa: PLC0415

    repo.add(replace(_report("rq-c", "how do I page orders", T0), consent_method="elicitation"),
             "how do i page orders", None, "m")  # fmt: skip
    repo.add_note(ReportNote("rn-c", "rq-c", "also", T0, consent_method="llm_attested"))
    got = repo.get("rq-c")
    assert got is not None
    assert got.consent_method == "elicitation"
    assert [n.consent_method for n in repo.notes("rq-c")] == ["llm_attested"]
