from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsJobParticipantOrAdmin, visible_jobs
from apps.jobs.models import Job

from .generate import generate_report, preview_html
from .models import ReportVersion
from .render import PdfEngineUnavailable


class _JobReportView(APIView):
    permission_classes = [IsAuthenticated, IsJobParticipantOrAdmin]

    def _job(self, request, pk):
        job = get_object_or_404(visible_jobs(Job.objects.all(), request.user), pk=pk)
        self.check_object_permissions(request, job)
        return job


def _describe(version: ReportVersion) -> dict:
    return {
        "id": version.id,
        "job_version": version.job_version,
        "template": str(version.template),
        "is_draft": version.issued_at is None,
        "issued_at": version.issued_at,
        "created_at": version.created_at,
        "has_pdf": bool(version.pdf_s3_key),
    }


class ReportPreviewView(_JobReportView):
    """The report as HTML, from live data. Opens in a tab; no PDF engine needed."""

    def get(self, request, pk):
        response = HttpResponse(preview_html(self._job(request, pk)), content_type="text/html; charset=utf-8")
        # Report text is escaped, but this page is also served from the API's
        # origin, so scripts are denied outright as a second line of defence.
        response["Content-Security-Policy"] = (
            "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data: https:"
        )
        return response


class ReportVersionsView(_JobReportView):
    """GET: the job's generated reports, newest first. POST: generate a draft PDF."""

    def get(self, request, pk):
        job = self._job(request, pk)
        return Response([_describe(v) for v in job.report_versions.select_related("template")])

    def post(self, request, pk):
        job = self._job(request, pk)
        if job.is_locked:
            return Response(
                {"code": "locked", "detail": "This job is issued. Its final report is already stored."}, status=409
            )
        try:
            version = generate_report(job, request.user)
        except PdfEngineUnavailable as exc:
            return Response({"code": "pdf_engine_unavailable", "detail": str(exc)}, status=503)
        return Response(_describe(version), status=201)


class ReportPdfView(_JobReportView):
    def get(self, request, pk, version_id):
        job = self._job(request, pk)
        version = get_object_or_404(ReportVersion, pk=version_id, job=job)
        if not version.pdf_s3_key or not default_storage.exists(version.pdf_s3_key):
            raise Http404("This report version has no stored PDF.")
        response = FileResponse(default_storage.open(version.pdf_s3_key), content_type="application/pdf")
        filename = f"{job.file_stem}.pdf"
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        return response
