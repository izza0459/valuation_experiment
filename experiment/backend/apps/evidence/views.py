from django.shortcuts import get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsJobParticipantOrAdmin, is_platform_admin, visible_jobs
from apps.jobs.models import Job
from apps.jobs.tabs import TabError, edit_denial

from . import dld, listing_parse, service


class _EvidenceView(APIView):
    permission_classes = [IsAuthenticated, IsJobParticipantOrAdmin]

    def _job(self, request, pk):
        job = get_object_or_404(visible_jobs(Job.objects.all(), request.user), pk=pk)
        self.check_object_permissions(request, job)
        return job

    @staticmethod
    def _fail(exc: TabError):
        return Response(exc.payload(), status=exc.status)


class EvidenceListView(_EvidenceView):
    """GET: the job's comparables, the latest AVM run and the sources a valuer
    can pick. POST: add a comparable entered by hand (ticked for the report)."""

    def get(self, request, pk):
        return Response(service.evidence_state(self._job(request, pk)))

    def post(self, request, pk):
        job = self._job(request, pk)
        try:
            return Response(service.add_comparable(job.pk, request.user, request.data), status=201)
        except TabError as exc:
            return self._fail(exc)


class EvidenceItemView(_EvidenceView):
    """PATCH: edit a comparable or tick/untick it (`selected`). DELETE: remove it."""

    def patch(self, request, pk, link_id):
        job = self._job(request, pk)
        try:
            return Response(service.update_comparable(job.pk, request.user, link_id, request.data))
        except TabError as exc:
            return self._fail(exc)

    def delete(self, request, pk, link_id):
        job = self._job(request, pk)
        try:
            service.remove_comparable(job.pk, request.user, link_id)
        except TabError as exc:
            return self._fail(exc)
        return Response(status=204)


class AvmView(_EvidenceView):
    """POST: run the AVM on the ticked comparables."""

    def post(self, request, pk):
        job = self._job(request, pk)
        try:
            return Response(service.run_avm(job.pk, request.user), status=201)
        except TabError as exc:
            return self._fail(exc)


# --- DLD sales and pasted listings ---------------------------------------------------


class DldDataView(APIView):
    """GET: how much DLD sales data is loaded. POST (admins): upload a DLD
    transactions CSV downloaded from DLD's open data."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        return Response(dld.data_status())

    def post(self, request):
        if not is_platform_admin(request.user):
            return Response({"code": "forbidden", "detail": "Only an admin can load DLD data."}, status=403)
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"code": "bad_request", "detail": "Choose the DLD transactions CSV file."}, status=400)
        try:
            result = dld.import_file(upload.file)
        except dld.DldFileError as exc:
            return Response({"code": "validation", "detail": str(exc)}, status=400)
        return Response({**result, **dld.data_status()}, status=201)


class JobDldView(_EvidenceView):
    """GET: DLD sales matching the filters (query string), or the job's
    defaults with no query. POST `{"ids": [...]}`: add those sales to the job."""

    def get(self, request, pk):
        job = self._job(request, pk)
        defaults = dld.defaults_for(job)
        params = {**defaults, **request.query_params.dict()} if request.query_params else defaults
        try:
            results = [dld.describe(t) for t in dld.search(params)]
        except (TypeError, ValueError):
            return Response({"code": "validation", "detail": "Check the filters."}, status=400)
        dld_links = job.job_comparables.filter(comparable__source="dld")
        linked = set(dld_links.values_list("comparable__source_ref", flat=True))
        for row in results:
            row["added"] = row["transaction_number"] in linked
        return Response({"filters": params, "defaults": defaults, "results": results, "data": dld.data_status()})

    def post(self, request, pk):
        job = self._job(request, pk)
        if denial := edit_denial(request.user, job, "evidence"):
            return self._fail(denial)
        ids = request.data.get("ids") if isinstance(request.data, dict) else None
        if not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids) or not ids:
            return Response({"code": "validation", "detail": "Choose at least one sale."}, status=400)
        return Response({"added": dld.add_to_job(job, ids)}, status=201)


class ParseListingView(_EvidenceView):
    """POST `{"text": ..., "link": ...}`: what can be read from a listing the
    valuer copied, to prefill the comparable form. Nothing is saved."""

    def post(self, request, pk):
        self._job(request, pk)
        body = request.data if isinstance(request.data, dict) else {}
        text, link = body.get("text"), body.get("link") or ""
        if not isinstance(text, str) or not text.strip() or not isinstance(link, str):
            return Response({"code": "validation", "detail": "Paste the listing's text."}, status=400)
        return Response(listing_parse.parse(text[:50_000], link[:1000]))
