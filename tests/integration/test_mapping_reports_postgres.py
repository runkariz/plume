"""PostgresMappingRepo against the real schema (migration 0019)."""

from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text

from plume.domain.reports.mapping import (
    MappingKind,
    MappingReport,
    MappingStatus,
    Suggestion,
    SuggestionStatus,
    VerifiedMapping,
    VerifiedStatus,
)
from plume.domain.reports.report import ReportNote
from plume.infrastructure.db.alembic_migrator import AlembicMigrator
from plume.infrastructure.db.repos.mapping_repo import PostgresMappingRepo

pytestmark = pytest.mark.integration
T0 = datetime(2026, 11, 22, 12, 0, tzinfo=UTC)
SUGGESTION = Suggestion(
    ("total",), ({"docId": "model:order", "quote": "Total amount.", "noQuote": None},), "GET /o"
)


@pytest.fixture
def repo(engine: Engine) -> Iterator[PostgresMappingRepo]:
    AlembicMigrator(engine).upgrade_to_head()

    def clean() -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM mapping_reports"))
            conn.execute(text("DELETE FROM verified_mappings"))

    clean()
    yield PostgresMappingRepo(engine)
    clean()


def _report(rid: str, field: str, kind: MappingKind, at: datetime) -> MappingReport:
    return MappingReport(
        report_id=rid, concept="order", concept_name="Order", api="shopify",
        canonical_field=field, kind=kind, problem="wrong", status=MappingStatus.OPEN,
        created_at=at, updated_at=at, build_id="b-1", session_hash="s1",
        suggestion=SUGGESTION, suggestion_status=SuggestionStatus.VALID,
    )  # fmt: skip


def test_add_dedupe_key_notes_save_list_and_purge(repo: PostgresMappingRepo) -> None:
    repo.add(_report("mr-a", "items[].sku", MappingKind.WRONG, T0), "items.sku")
    repo.add(_report("mr-b", "total", MappingKind.MISSING, T0), "total")
    found = repo.by_key("order", "shopify", "Items.SKU", "wrong")
    assert found is not None
    assert found.report_id == "mr-a"
    assert found.suggestion == SUGGESTION
    assert repo.by_key("order", "shopify", "items[].sku", "missing") is None
    repo.add_note(ReportNote("mn-1", "mr-a", "also", T0 + timedelta(minutes=1), session_hash="s1"))
    a = repo.get("mr-a")
    assert a is not None
    assert (a.report_count, a.note_count) == (2, 1)
    assert [n.text for n in repo.notes("mr-a")] == ["also"]
    assert repo.writes_since("s1", T0 - timedelta(minutes=5)) == 3
    assert [r.report_id for r in repo.list_reports("shopify", "order", None, None)] == [
        "mr-a",
        "mr-b",
    ]
    assert [r.report_id for r in repo.find("order", "shopify", "total", 5)] == ["mr-b"]
    repo.save(replace(a, status=MappingStatus.ROUTED, route="stream", reason="gap"))
    routed = repo.get("mr-a")
    assert routed is not None
    assert (routed.status, routed.route) == (MappingStatus.ROUTED, "stream")
    assert repo.purge_open(T0 + timedelta(days=200)) == 1  # mr-b (open); mr-a is routed
    assert repo.get("mr-b") is None


def test_verified_mappings_upsert_per_concept_field_and_api(repo: PostgresMappingRepo) -> None:
    m = VerifiedMapping("vm-1", "order", "grandTotal", "shopify", SUGGESTION, "b-1", "mr-a",
                        VerifiedStatus.ACTIVE, T0, T0)  # fmt: skip
    repo.put_verified(m)
    repo.put_verified(replace(m, status=VerifiedStatus.SUSPENDED, suspended_reason="gone",
                              canonical_field="grand_total", build_id="b-2"))  # fmt: skip
    (only,) = repo.verified("order", "shopify")
    assert (only.status, only.suspended_reason, only.build_id) == (
        VerifiedStatus.SUSPENDED,
        "gone",
        "b-2",
    )
    assert only.suggestion == SUGGESTION
    assert repo.verified_for("order", "shopify", ["GrandTotal"]) == [only]
    assert repo.verified("order", "shopify", "active") == []
