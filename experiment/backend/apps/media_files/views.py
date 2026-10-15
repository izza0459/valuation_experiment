"""Photo and document endpoints: `/api/jobs/<id>/photos/...` and `.../documents/...`.

    GET    <kind>/                 list, plus what the user may do and what is still needed
    POST   <kind>/                 upload (multipart, field `files`, several at once)
    PATCH  <kind>/<id>/            caption, include in report, type  (body carries `base_version`)
    DELETE <kind>/<id>/            hide it
    POST   <kind>/reorder/         body {"ids": [...]}: the full new order
    GET    <kind>/<id>/file/       the stored file;  <kind>/<id>/thumb/  its thumbnail

Both kinds share one implementation; the URL says which (`kind` below).
"""

from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsJobParticipantOrAdmin, visible_jobs
from apps.jobs.models import Job
from apps.jobs.tabs import TabError, VersionConflict, edit_denial
from apps.presets.options import options_for

from . import service
from .checks import EXEC_SUMMARY_PHOTOS, requirements
from .models import Photo
from .processing import MAX_BYTES


def describe(item, job) -> dict:
    kind = service.PHOTOS if isinstance(item, Photo) else service.DOCUMENTS
    base = f"/api/jobs/{job.pk}/{kind.name}/{item.pk}"
    data = {
        "id": item.pk,
        "caption": item.caption,
        "order": item.order,
        "include_in_report": item.include_in_report,
        "original_name": item.original_name,
        "content_type": item.content_type,
        "size_bytes": item.size_bytes,
        "edit_version": item.edit_version,
        "uploaded_at": item.uploaded_at,
        "uploaded_by": str(item.uploaded_by) if item.uploaded_by else "",
        "url": f"{base}/file/",
        "thumb_url": f"{base}/thumb/",
    }
    if kind is service.PHOTOS:
        data.update(slot=item.slot, width=item.width, height=item.height)
    else:
        data.update(doc_type=item.doc_type, page_count=item.page_count, is_pdf=item.content_type == "application/pdf")
    return data


class _MediaView(APIView):
    permission_classes = [IsAuthenticated, IsJobParticipantOrAdmin]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    kind = None  # set by as_view(kind=...)

    def _kind(self):
        return service.KINDS[self.kind]

    def _job(self, request, pk):
        job = get_object_or_404(visible_jobs(Job.objects.all(), request.user), pk=pk)
        self.check_object_permissions(request, job)
        return job

    def _fail(self, exc: TabError, job):
        payload = exc.payload()
        if isinstance(exc, VersionConflict):
            current = payload.pop("current", None)
            payload["current"] = describe(current, job) if current is not None else None
        return Response(payload, status=exc.status)


class MediaListView(_MediaView):
    def get(self, request, pk):
        job, kind = self._job(request, pk), self._kind()
        denial = edit_denial(request.user, job, kind.name)
        return Response(
            {
                "items": [describe(i, job) for i in kind.model.objects.filter(job=job)],
                "can_edit": denial is None,
                "read_only_reason": denial.detail if denial else "",
                "needs": [{"label": label, "met": met} for label, met in requirements(job, kind.name)],
                "limits": {
                    "max_items": kind.max_items,
                    "max_file_mb": MAX_BYTES // (1024 * 1024),
                    "files_per_upload": service.FILES_PER_REQUEST,
                    "accepts": service.accepted_text(kind),
                    "exec_summary_photos": EXEC_SUMMARY_PHOTOS,
                },
                "doc_types": (
                    [{"value": o["value"], "label": o["label"]} for o in options_for("document_type")]
                    if kind is service.DOCUMENTS
                    else []
                ),
            }
        )

    def post(self, request, pk):
        job, kind = self._job(request, pk), self._kind()
        files = request.FILES.getlist("files")
        if not files:
            return Response({"code": "bad_request", "detail": "Choose at least one file."}, status=400)
        try:
            result = service.upload(
                job.pk, request.user, kind, files,
                slot=request.data.get("slot") or None, doc_type=request.data.get("doc_type") or None,
            )
        except TabError as exc:
            return self._fail(exc, job)
        body = {"created": [describe(i, job) for i in result.created], "rejected": result.rejected}
        if not result.created:
            body.update(code="rejected", detail="None of the files could be added.")
            return Response(body, status=400)
        return Response(body, status=201)


class MediaItemView(_MediaView):
    def patch(self, request, pk, item_id):
        job, kind = self._job(request, pk), self._kind()
        body = request.data if isinstance(request.data, dict) else {}
        changes = {k: v for k, v in body.items() if k != "base_version"}
        try:
            item = service.update(job.pk, request.user, kind, item_id, body.get("base_version"), changes)
        except TabError as exc:
            return self._fail(exc, job)
        except LookupError:
            raise Http404 from None
        return Response(describe(item, job))

    def delete(self, request, pk, item_id):
        job, kind = self._job(request, pk), self._kind()
        try:
            service.remove(job.pk, request.user, kind, item_id)
        except TabError as exc:
            return self._fail(exc, job)
        except LookupError:
            raise Http404 from None
        return Response(status=204)


class MediaReorderView(_MediaView):
    def post(self, request, pk):
        job, kind = self._job(request, pk), self._kind()
        body = request.data if isinstance(request.data, dict) else {}
        try:
            items = service.reorder(job.pk, request.user, kind, body.get("ids"))
        except VersionConflict as exc:
            current = [describe(i, job) for i in kind.model.objects.filter(job=job)]
            return Response({**exc.payload(), "current": current}, status=exc.status)
        except TabError as exc:
            return self._fail(exc, job)
        return Response([describe(i, job) for i in items])


class MediaFileView(_MediaView):
    """The stored file or its thumbnail, behind the same access check as the
    job: a stored file is never reachable by a guessable public URL."""

    thumb = False

    def get(self, request, pk, item_id):
        job, kind = self._job(request, pk), self._kind()
        item = get_object_or_404(kind.model.objects.filter(job=job), pk=item_id)
        key = item.thumb_key if self.thumb else item.s3_key
        if not key or not default_storage.exists(key):
            raise Http404("The stored file is missing.")
        content_type = "image/jpeg" if self.thumb else (item.content_type or "application/octet-stream")
        response = FileResponse(default_storage.open(key), content_type=content_type)
        name = (item.original_name or f"{kind.name}-{item.pk}").replace('"', "")
        if not self.thumb and content_type == "image/jpeg" and not name.lower().endswith((".jpg", ".jpeg")):
            name = f"{name.rsplit('.', 1)[0]}.jpg"
        response["Content-Disposition"] = f'inline; filename="{name}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, max-age=300"
        return response
