from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsJobParticipantOrAdmin, visible_jobs
from apps.jobs.models import Job
from apps.jobs.tabs import TabError

from . import service


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
