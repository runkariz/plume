"""Maintainer API for reported questions: list, read with notes, set the status."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Query

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
