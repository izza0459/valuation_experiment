from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsJobParticipantOrAdmin, visible_jobs
from apps.jobs.models import Job
from apps.jobs.tabs import TabError

from .delivery import describe_delivery, request_delivery
from .tasks import request_send
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
            "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data: https:; "
            "frame-ancestors 'self'"
        )
        # The Review & Send tab shows it inline for the reviewer.
        response["X-Frame-Options"] = "SAMEORIGIN"
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


class ReportDeliveryView(_JobReportView):
    """GET: who the issued report has been sent to. POST: send it to someone at
    the bank — `{"email": ..., "name": ..., "message": ...}`. Only the admin who
    took the instruction (or a platform admin), and only once it is issued."""

    def get(self, request, pk):
        job = self._job(request, pk)
        return Response([describe_delivery(d) for d in job.deliveries.select_related("requested_by")])

    def post(self, request, pk):
        job = self._job(request, pk)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            delivery = request_delivery(job, request.user, body.get("email"), body.get("name"), body.get("message"))
        except TabError as exc:  # not allowed, not issued yet, or a bad address
            return Response(exc.payload(), status=exc.status)
        request_send(delivery.pk)
        delivery.refresh_from_db()
        return Response(describe_delivery(delivery), status=201)
