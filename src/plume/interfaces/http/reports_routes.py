"""Maintainer API for reported questions and mapping reports: list, read with notes, set the
status (and verified mappings)."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from plume.application.reports.mappings import MappingReports
from plume.application.reports.service import ReportedQuestions
from plume.interfaces.http import schemas as s
from plume.interfaces.http.maintainer import make_auth


def reports_router(reports: Callable[[], ReportedQuestions], tokens: tuple[str, ...]) -> APIRouter:
    router = APIRouter(dependencies=[Depends(make_auth(tokens))], tags=["maintainer"])

    @router.get("/v1/maintainer/reports", response_model=s.ReportList)
    def list_reports(
        api: Annotated[str | None, Query()] = None,
        status: Annotated[str | None, Query()] = None,
    ) -> s.ReportList:
        """Reported questions, most reported first (readers' LLMs reported Plume could not
        answer them)."""
        svc = reports()
        items = svc.list_reports(api, status)
        return s.ReportList(reports=[s.ReportOut(**r) for r in items], enabled=svc.enabled)

    @router.get("/v1/maintainer/reports/{report_id}", response_model=s.ReportOut)
    def get_report(report_id: str) -> s.ReportOut:
        return s.ReportOut(**reports().get(report_id))

    @router.patch("/v1/maintainer/reports/{report_id}", response_model=s.ReportOut)
    def set_report_status(report_id: str, body: s.ReportStatusUpdate) -> s.ReportOut:
        """Label a report: answered / search-miss / package-gap / out-of-scope (or open), with
        a short reason (answered and out-of-scope reasons are shown to readers)."""
        return s.ReportOut(**reports().set_status(report_id, body.status, body.reason))

    return router


def mapping_reports_router(
    mappings: Callable[[], MappingReports], tokens: tuple[str, ...]
) -> APIRouter:
    router = APIRouter(dependencies=[Depends(make_auth(tokens))], tags=["maintainer"])

    @router.get("/v1/maintainer/mapping-reports", response_model=s.MappingReportList)
    def list_mapping_reports(
        api: Annotated[str | None, Query()] = None,
        concept: Annotated[str | None, Query(description='e.g. "inventory/stock"')] = None,
        status: Annotated[str | None, Query()] = None,
        kind: Annotated[str | None, Query()] = None,
    ) -> s.MappingReportList:
        """Canonical-model mapping reports, most reported first."""
        svc = mappings()
        items = svc.list_reports(api, concept, status, kind)
        return s.MappingReportList(
            reports=[s.MappingReportOut(**r) for r in items], enabled=svc.enabled
        )

    @router.get("/v1/maintainer/mapping-reports/{report_id}", response_model=s.MappingReportOut)
    def get_mapping_report(report_id: str) -> s.MappingReportOut:
        return s.MappingReportOut(**mappings().get(report_id))

    @router.patch("/v1/maintainer/mapping-reports/{report_id}", response_model=s.MappingReportOut)
    def act_on_mapping_report(report_id: str, body: s.MappingReportAction) -> s.MappingReportOut:
        """accept (a validated suggestion becomes the verified mapping, re-validated first),
        reject (the reason is shown to readers), route (plume / stream / owner) or reopen."""
        return s.MappingReportOut(**mappings().act(report_id, body.action, body.reason, body.route))

    @router.get("/v1/maintainer/verified-mappings", response_model=s.VerifiedMappingList)
    def list_verified_mappings(
        api: Annotated[str | None, Query()] = None,
        concept: Annotated[str | None, Query()] = None,
        status: Annotated[str | None, Query(description="active | suspended")] = None,
    ) -> s.VerifiedMappingList:
        """Verified mappings (re-validated against each API's current build first)."""
        items = mappings().verified_list(concept, api, status)
        return s.VerifiedMappingList(mappings=[s.VerifiedMappingOut(**m) for m in items])

    return router
