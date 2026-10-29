import datetime

from django.db.models import Q
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import (
    CanCreateJobs,
    IsJobParticipantOrAdmin,
    IsPlatformAdmin,
    team_condition,
    visible_jobs,
)
from apps.presets.options import options_for, user_options

from .field_config import TABS, serialize_config
from .intake import create_job
from .models import Job, JobTransition
from .serializers import JobDetailSerializer, JobListSerializer
from .tabs import TabError, accept_reviewer_edits, job_tab_state, patch_tab, set_report_exclusions
from .transitions import perform_transition, transition_log
from .workflow import JobStatus


class FieldConfigView(APIView):
    """Serves the 9-tab field config so the frontend form engine and the
    backend validate against the same source of truth (CLAUDE.md §8)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(serialize_config())


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """Hands the browser its CSRF cookie. Session auth requires the token on
    every unsafe request (the tab PATCH, for one), and the SPA has no
    server-rendered page to receive the cookie from."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        # Also in the body: when the API is on another domain the cookie
        # isn't readable from the app, but the token can still be echoed back.
        return Response({"csrfToken": get_token(request)})


class OptionsView(APIView):
    """Everything the form's dropdowns offer, keyed by the field config's
    `options_key`, in one request. Validation resolves values against the
    same source (apps.presets.options), so the two can't disagree."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        keys = {}
        for tab in TABS:
            for f in tab["fields"]:
                if f["options_key"]:
                    keys[f["options_key"]] = f["free_text"]
        payload = {key: options_for(key, free_text=free) for key, free in keys.items()}
        payload["users"] = user_options()
        return Response(payload)


class JobViewSet(mixins.CreateModelMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsJobParticipantOrAdmin]

    def get_permissions(self):
        # Ops (or an admin) takes the instruction in (CLAUDE.md §3).
        if self.action == "create":
            return [IsAuthenticated(), CanCreateJobs()]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        """POST {"values": {...}}: see apps.jobs.intake for what may be set."""
        body = request.data if isinstance(request.data, dict) else {}
        try:
            job = create_job(request.user, body.get("values"))
        except TabError as exc:
            return Response(exc.payload(), status=exc.status)
        return Response(
            {"id": job.pk, "bayut_internal_reference_no": job.bayut_internal_reference_no}, status=201
        )

    def get_queryset(self):
        """Scoped to the jobs this user holds a role on (CLAUDE.md §7
        RBAC); platform admins see all. Soft-deleted jobs are excluded by
        the default manager."""
        queryset = visible_jobs(
            Job.objects.select_related(
                "bank", "property", "summary", "checklist", "inspection", "location", "valuation", "scheduling",
                "valuer", "registered_valuer",
            ),
            self.request.user,
        )

        params = self.request.query_params

        # Dashboard filters (design brief S1).
        if status := params.get("status"):
            queryset = queryset.filter(status=status)
        if bank := params.get("bank"):
            queryset = queryset.filter(bank_id=bank)
        if valuer := params.get("valuer"):
            queryset = queryset.filter(Q(valuer_id=valuer) | Q(registered_valuer_id=valuer))
        # The dashboard's stage and section cards filter the list to their jobs.
        if ids := params.get("ids"):
            queryset = queryset.filter(pk__in=[int(i) for i in ids.split(",") if i.strip().isdigit()])
        if property_type := params.get("type"):
            queryset = queryset.filter(summary__property_category=property_type)
        if search := params.get("q"):
            queryset = queryset.filter(
                Q(bayut_internal_reference_no__icontains=search)
                | Q(bank_reference_no__icontains=search)
                | Q(client_name__icontains=search)
                | Q(property__building_name__icontains=search)
                | Q(property__community_name__icontains=search)
                | Q(property__unit_number__icontains=search)
            )

        # "My jobs" / "My team" / "Awaiting my review" / "Lost" views. Lost leads
        # only show under Lost (or when a dashboard card names them).
        view = params.get("view")
        user = self.request.user
        if view == "lost":
            queryset = queryset.filter(status=JobStatus.LOST)
        elif self.action == "list" and not ids and not params.get("status"):
            queryset = queryset.exclude(status=JobStatus.LOST)
        if view == "team":
            queryset = queryset.filter(team_condition(user.team_ids()))
        elif view == "mine":
            queryset = queryset.filter(
                Q(valuer=user) | Q(registered_valuer=user) | Q(inspected_by=user) | Q(admin_user=user)
            )
        elif view == "review":
            queryset = queryset.filter(status=JobStatus.PEER_REVIEW, peer_reviewer=user)

        return queryset

    def get_serializer_class(self):
        if self.action == "list":
            return JobListSerializer
        return JobDetailSerializer


class JobTabView(APIView):
    """Read or partially update one tab of a job (design brief S3).

    PATCH body: `{"base_version": <int>, "values": {<field>: <value>, ...}}`
    where `base_version` is the tab version the client last saw. Only the
    named fields change. A stale version is refused with 409 so the first
    save wins and the second is told, rather than silently overwritten."""

    permission_classes = [IsAuthenticated, IsJobParticipantOrAdmin]

    def _job(self, request, pk):
        job = get_object_or_404(visible_jobs(Job.objects.all(), request.user), pk=pk)
        self.check_object_permissions(request, job)
        return job

    def get(self, request, pk, tab):
        job = self._job(request, pk)
        state = job_tab_state(job, request.user)
        if tab not in state:
            return Response({"code": "unknown_tab", "detail": f"No such tab: {tab}."}, status=404)
        return Response({"tab": tab, **state[tab]})

    def patch(self, request, pk, tab):
        job = self._job(request, pk)
        body = request.data if isinstance(request.data, dict) else {}
        base_version = body.get("base_version")
        if isinstance(base_version, bool) or not isinstance(base_version, int) or base_version < 0:
            return Response(
                {"code": "bad_request", "detail": "`base_version` is required: the tab version you loaded."},
                status=400,
            )
        try:
            return Response(patch_tab(job.pk, tab, request.user, body.get("values"), base_version))
        except TabError as exc:
            return Response(exc.payload(), status=exc.status)


class JobTransitionView(APIView):
    """GET: the job's lifecycle history with review comments. POST: make a move.

    POST body: `{"from": <status the client saw>, "to": <status>, "comments": ""}`.
    Errors: 403 role, 409 stale/not allowed/locked, 400 missing comment,
    422 when a gate blocks it (body lists the `blockers`)."""

    permission_classes = [IsAuthenticated, IsJobParticipantOrAdmin]

    def _job(self, request, pk):
        job = get_object_or_404(visible_jobs(Job.objects.all(), request.user), pk=pk)
        self.check_object_permissions(request, job)
        return job

    def get(self, request, pk):
        return Response(transition_log(self._job(request, pk)))

    def post(self, request, pk):
        job = self._job(request, pk)
        body = request.data if isinstance(request.data, dict) else {}
        from_status, to_status = body.get("from"), body.get("to")
        if not isinstance(from_status, str) or not isinstance(to_status, str):
            return Response({"code": "bad_request", "detail": "`from` and `to` are required."}, status=400)
        comments = body.get("comments", "")
        if not isinstance(comments, str):
            return Response({"code": "bad_request", "detail": "`comments` must be text."}, status=400)
        try:
            job = perform_transition(job.pk, request.user, from_status, to_status, comments)
        except TabError as exc:
            return Response(exc.payload(), status=exc.status)
        # 202 when an issue was queued for the background worker rather than done.
        return Response(
            {"status": job.status, "status_label": job.get_status_display(), "issuing": job.issue_in_progress},
            status=202 if job.issue_in_progress else 200,
        )


class JobReviseView(APIView):
    """POST: start a new version of an issued job (CLAUDE.md §3: a re-issue
    keeps the old version and creates a new one). Admins only; once per version."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def post(self, request, pk):
        from django.db import transaction

        from apps.audit.middleware import acting_as

        job = get_object_or_404(Job.objects.all(), pk=pk)
        with acting_as(request.user), transaction.atomic():
            job = Job.objects.select_for_update().get(pk=job.pk)
            if not job.is_locked:
                return Response(
                    {"code": "not_issued", "detail": "Only an issued job can be revised."}, status=409
                )
            if existing := job.reissues.first():
                return Response(
                    {
                        "code": "already_revised",
                        "detail": f"This version already has a revision ({existing.bayut_internal_reference_no}).",
                        "id": existing.pk,
                    },
                    status=409,
                )
            revision = job.create_revision(by=request.user)
            JobTransition.objects.create(
                job=revision,
                from_status=JobStatus.ISSUED,
                to_status=revision.status,
                by=request.user,
                comments=f"Revision of {job.bayut_internal_reference_no} (v{job.version}).",
            )
        return Response(
            {"id": revision.pk, "reference": revision.bayut_internal_reference_no, "version": revision.version},
            status=201,
        )


class JobReportFieldsView(APIView):
    """POST {"excluded": ["summary.departures", ...]}: the Preliminary Check
    and Inspection fields to leave out of the report."""

    permission_classes = [IsAuthenticated, IsJobParticipantOrAdmin]

    def post(self, request, pk):
        job = get_object_or_404(Job.objects.all(), pk=pk)
        self.check_object_permissions(request, job)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            excluded = set_report_exclusions(job.pk, request.user, body.get("excluded"))
        except TabError as exc:
            return Response(exc.payload(), status=exc.status)
        return Response({"excluded": excluded})


class JobCallView(APIView):
    """POST {"call_status", "call_remark", "inspection_booked_at"}: log one call
    on the Scheduling stage (the Save call button, CRM feedback SC-03/SC-04)."""

    permission_classes = [IsAuthenticated, IsJobParticipantOrAdmin]

    def post(self, request, pk):
        from .calls import log_call

        job = get_object_or_404(Job.objects.all(), pk=pk)
        self.check_object_permissions(request, job)
        try:
            return Response(log_call(job.pk, request.user, request.data), status=201)
        except TabError as exc:
            return Response(exc.payload(), status=exc.status)


class JobReviewerEditsView(APIView):
    """POST: the valuer accepts the peer reviewer's wording changes (CRM
    feedback PR-01), which lets the reviewer sign off."""

    permission_classes = [IsAuthenticated, IsJobParticipantOrAdmin]

    def post(self, request, pk):
        job = get_object_or_404(Job.objects.all(), pk=pk)
        self.check_object_permissions(request, job)
        try:
            accepted = accept_reviewer_edits(job.pk, request.user)
        except TabError as exc:
            return Response(exc.payload(), status=exc.status)
        return Response({"accepted": accepted})


class JobLostView(APIView):
    """GET: the reasons a lead can be lost for. POST {"reason", "note"}: mark
    it lost (final)."""

    permission_classes = [IsAuthenticated, IsJobParticipantOrAdmin]

    def get(self, request, pk):
        from .lost import reasons

        return Response({"reasons": reasons()})

    def post(self, request, pk):
        from .lost import mark_lost

        job = get_object_or_404(visible_jobs(Job.objects.all(), request.user), pk=pk)
        self.check_object_permissions(request, job)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            job = mark_lost(job.pk, request.user, body.get("reason"), body.get("note"))
        except TabError as exc:
            return Response(exc.payload(), status=exc.status)
        return Response({"status": job.status, "status_label": job.get_status_display()})


class JobActivityView(APIView):
    """The lead's activity for the workspace's right panel, newest first: stage
    moves (with review comments and lost reasons), calls, report sends and
    field changes, read off the lifecycle log and the audit trail."""

    permission_classes = [IsAuthenticated, IsJobParticipantOrAdmin]

    # Bookkeeping columns that change with real edits; not worth listing.
    QUIET = {"updated_at", "version", "status", "tracker_coi_check", "issue_requested_at", "issue_requested_by",
             "inspection_scheduled_at", "inspected_at", "countersigned_at", "countersigned_by", "lost_at",
             "lost_by", "lost_from_status", "lost_reason", "lost_note", "coi_confirmed_at", "coi_confirmed_by"}

    def get(self, request, pk):
        from apps.audit.models import AuditLog

        from .transitions import transition_log

        job = get_object_or_404(visible_jobs(Job.objects.all(), request.user), pk=pk)
        self.check_object_permissions(request, job)

        labels = {f["key"]: f["label"] for tab in TABS for f in tab["fields"]}
        items = []
        for t in transition_log(job):
            items.append({"kind": "lost" if t["to_status"] == JobStatus.LOST else "stage",
                          "title": "Marked lost" if t["to_status"] == JobStatus.LOST else t["label"],
                          "detail": t["comments"], "who": t["who"], "at": t["at"]})
        for c in job.call_attempts.select_related("by"):
            items.append({"kind": "call", "title": f"Call: {c.get_status_display()}", "detail": c.remark,
                          "who": str(c.by) if c.by else "", "at": c.at})
        for d in job.deliveries.select_related("requested_by"):
            items.append({"kind": "send", "title": f"Report sent to {d.recipient_name or d.recipient_email}",
                          "detail": d.get_status_display(), "who": str(d.requested_by) if d.requested_by else "",
                          "at": d.requested_at})
        entries = AuditLog.objects.filter(job=job).select_related("changed_by").order_by("-changed_at")[:150]
        for e in entries:
            if e.field_name in self.QUIET or e.field_name.endswith("_id") and e.field_name[:-3] in self.QUIET:
                continue
            label = labels.get(e.field_name) or labels.get(e.field_name.removesuffix("_id")) or (
                e.field_name.replace("_", " ").capitalize())
            items.append({"kind": "edit", "title": f"{label} changed", "detail": "",
                          "old": e.old_value, "new": e.new_value,
                          "who": str(e.changed_by) if e.changed_by else "System", "at": e.changed_at})
        items.sort(key=lambda i: i["at"], reverse=True)
        return Response(items[:150])


class JobFunnelView(APIView):
    """GET: the admin pipeline funnel (CRM feedback DB-01, DB-02), or with
    `?stage=` the counts by section within one stage (DB-03). Dates: `range`
    = today / week / month / 30d, or `from` / `to` (YYYY-MM-DD). Admins only."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.accounts.permissions import dashboard_jobs

        from . import dashboard

        params = request.query_params
        try:
            begin, end = dashboard.date_range(params.get("range"), params.get("from"), params.get("to"))
        except ValueError:
            return Response({"code": "validation", "detail": "Dates must be YYYY-MM-DD."}, status=400)
        jobs = dashboard_jobs(Job.objects.all(), request.user)
        stage = params.get("stage")
        if stage:
            if stage not in dict(dashboard.STAGES):
                return Response({"code": "validation", "detail": "No such stage."}, status=400)
            return Response({"stage": stage, "sections": dashboard.sections(jobs, stage, begin, end)})
        return Response(dashboard.funnel(jobs, begin, end))


class DashboardView(APIView):
    """GET: the Dashboard tab. An admin sees every lead; a manager their own
    and their team's; anyone else their own. `person` narrows it to one
    person; dates as for the funnel."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.contrib.auth import get_user_model

        from apps.accounts.permissions import dashboard_jobs, is_platform_admin

        from . import dashboard

        params = request.query_params
        try:
            begin, end = dashboard.date_range(params.get("range"), params.get("from"), params.get("to"))
        except ValueError:
            return Response({"code": "validation", "detail": "Dates must be YYYY-MM-DD."}, status=400)
        person = params.get("person")
        person = int(person) if person and person.isdigit() else None
        user = request.user
        jobs = dashboard_jobs(Job.objects.all(), user, person)
        users = get_user_model().objects.filter(is_active=True)
        if is_platform_admin(user):
            scope = "all"
        else:
            team = user.team_ids()
            users = users.filter(pk__in=team)
            scope = "team" if len(team) > 1 else "mine"
        people = [{"id": u.pk, "name": str(u)} for u in users.order_by("first_name", "last_name", "email")]
        return Response({"scope": scope, "people": people if scope != "mine" else [],
                         **dashboard.overview(jobs, begin, end)})


class JobKpiView(APIView):
    """Dashboard KPI strip (design brief S1).

    Only reports what the data model can actually support. "Due today"
    needs a per-bank SLA/due date, which doesn't exist yet — it's omitted
    rather than estimated, so nothing on the dashboard is invented.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.utils import timezone

        jobs = visible_jobs(Job.objects.all(), request.user)
        week_ago = timezone.now() - datetime.timedelta(days=7)
        turnaround = self._average_turnaround(jobs.filter(status=JobStatus.ISSUED, issued_at__isnull=False))

        return Response(
            {
                "in_progress": jobs.exclude(status__in=[JobStatus.ISSUED, JobStatus.LOST]).count(),
                "awaiting_peer_review": jobs.filter(status=JobStatus.PEER_REVIEW).count(),
                "issued_this_week": jobs.filter(status=JobStatus.ISSUED, issued_at__gte=week_ago).count(),
                "avg_turnaround_hours": (
                    round(turnaround.total_seconds() / 3600, 1) if turnaround is not None else None
                ),
            }
        )

    @staticmethod
    def _average_turnaround(issued):
        """Instruction to issue (CLAUDE.md §7), measured from when the bank's
        request arrived; failing that, the start of the instruction date (in
        Dubai time); failing that, when the job was keyed in."""
        from django.utils import timezone

        durations = []
        for received, instructed, created, issued_at in issued.values_list(
            "date_time_request_received", "date_of_instruction", "created_at", "issued_at"
        ):
            if received is not None:
                start = received
            elif instructed is not None:
                start = timezone.make_aware(datetime.datetime.combine(instructed, datetime.time.min))
            else:
                start = created
            durations.append(issued_at - start)
        return sum(durations, datetime.timedelta()) / len(durations) if durations else None
