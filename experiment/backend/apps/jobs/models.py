import builtins

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import MaxValueValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.common.models import (
    AllObjectsManager,
    SoftDeleteManager,
    SoftDeleteModel,
    SoftDeleteQuerySet,
)

from . import calculations
from .constants import ECONOMIC_LIFE_YEARS, PLOT_BEARING_CATEGORIES, REPAIRS_DEFAULT
from .workflow import (
    IssueBlockedError,
    JobLockedError,
    JobStatus,
    TransitionError,
    validate_issue_preconditions,
    validate_transition,
)


def split_names(stored: str) -> list[str]:
    """Names stored one per line back to a list."""
    return [n.strip() for n in (stored or "").splitlines() if n.strip()]


class Property(SoftDeleteModel):
    """Standalone so the same property can be referenced by multiple Job
    versions/instructions over time — needed for the conflict check
    (CLAUDE.md §7: "warn if the property or applicant was valued before")."""

    unit_number = models.CharField(max_length=100, blank=True)
    building_name = models.CharField(max_length=255, blank=True)
    # Between building and community (e.g. The Views); the report's address uses it.
    development = models.CharField(max_length=255, blank=True)
    community_name = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # One or more names, one per line (several owners or applicants is common);
    # the form edits them as a list (field type "names").
    applicant_name = models.TextField(blank=True)
    ownership_name = models.TextField(blank=True)

    TITLE_DOC_TYPES = [
        ("title_deed", "Title Deed"),
        ("site_plan", "Site Plan"),
        ("site_affection_plan", "Site Affection Plan"),
        ("spa", "SPA"),
        ("ownership_certificate", "Ownership Certificate"),
        ("ownership_deed", "Ownership Deed"),
        ("usufruct_certificate", "Usufruct Certificate"),
        ("initial_contract_of_sale", "Initial Contract of Sale"),
        ("initial_sale_certificate", "Initial Sale Certificate"),
        ("pre_registration_certificate", "Pre-Registration Certificate"),
        ("oqood", "Oqood"),
        ("other", "Other"),
    ]
    title_doc_type = models.CharField(max_length=40, choices=TITLE_DOC_TYPES, blank=True)
    title_doc_property_no = models.CharField(max_length=100, blank=True)
    title_doc_plot_no = models.CharField(max_length=100, blank=True)
    title_doc_municipality_no = models.CharField(max_length=100, blank=True)
    title_doc_building_no = models.CharField(max_length=100, blank=True)
    # The document's own spelling, when it differs from the address above.
    title_doc_building_name = models.CharField(max_length=255, blank=True)
    title_doc_community_name = models.CharField(max_length=255, blank=True)
    title_doc_emirate = models.CharField(max_length=50, default="Dubai")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "properties"

    def __str__(self):
        return f"{self.unit_number} {self.building_name}, {self.community_name}".strip()

    def save(self, *args, **kwargs):
        """The address on an issued report is part of what was signed, so a
        property that a locked job points at can't be edited. (Revisions get
        their own copy in Job.create_revision, so amending one never needs to.)"""
        if self.pk:
            locked = list(
                Job.all_objects.filter(property_id=self.pk, is_locked=True)
                .values_list("bayut_internal_reference_no", flat=True)
            )
            if locked:
                raise JobLockedError(
                    f"Property is used by issued job {', '.join(locked)} and cannot be modified."
                )
        super().save(*args, **kwargs)

    @property
    def gps_dms(self) -> str:
        return calculations.lat_long_to_dms(self.latitude, self.longitude)

    @property
    def applicant_names(self) -> list[str]:
        return split_names(self.applicant_name)

    @property
    def ownership_names(self) -> list[str]:
        return split_names(self.ownership_name)

    @property
    def address_as_per_document(self) -> str:
        return calculations.format_address_as_per_document(
            self.title_doc_property_no,
            self.title_doc_plot_no,
            self.title_doc_municipality_no,
            self.title_doc_building_no,
            self.title_doc_building_name or self.building_name,
            self.title_doc_community_name or self.community_name,
            self.title_doc_emirate,
        )


class ReferenceCounter(models.Model):
    """Monotonic per-year allocator for Bayut reference numbers.

    Deriving the next number from existing Job rows (a count or a max)
    reuses a reference once a job is deleted — and a reference that has
    appeared on an issued bank report must never be handed out twice.
    """

    year = models.PositiveIntegerField(unique=True)
    last_value = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"ReferenceCounter<{self.year}:{self.last_value}>"

    @classmethod
    def next_for_year(cls, year: int) -> int:
        with transaction.atomic():
            cls.objects.get_or_create(year=year)
            counter = cls.objects.select_for_update().get(year=year)
            counter.last_value += 1
            counter.save(update_fields=["last_value"])
            return counter.last_value


class JobQuerySet(SoftDeleteQuerySet):
    def delete(self):
        """An issued job is a regulatory record. `Job.save()` already
        refuses to touch a locked row, but a bulk delete goes straight to
        UPDATE — so the same rule has to hold here or it's bypassed by
        selecting two rows instead of one."""
        locked = self.filter(is_locked=True).values_list("bayut_internal_reference_no", flat=True)
        if locked:
            raise JobLockedError(
                f"Refusing to delete issued job(s): {', '.join(locked)}. "
                f"Issued work is retained for {settings.VALUATION_RETENTION_YEARS} years "
                f"(DLD 67/2020)."
            )
        return super().delete()


class JobManager(SoftDeleteManager):
    queryset_class = JobQuerySet


class JobAllObjectsManager(AllObjectsManager):
    queryset_class = JobQuerySet


class Job(SoftDeleteModel):
    """A single valuation instruction/engagement. `version` + `parent_job`
    implement re-issue-creates-a-new-version (CLAUDE.md §3)."""

    objects = JobManager()
    all_objects = JobAllObjectsManager()

    PURPOSE_CHOICES = [
        ("mortgage_security", "Mortgage Security"),
        ("audit_purpose", "Audit Purpose"),
        ("internal_purpose", "Internal Purpose"),
    ]

    # Refs & dates (Tab 2)
    bank_reference_no = models.CharField(max_length=100, blank=True)
    bayut_internal_reference_no = models.CharField(max_length=50, unique=True, editable=False)
    date_time_request_received = models.DateTimeField(null=True, blank=True)
    date_of_instruction = models.DateField(null=True, blank=True)

    # Mortgage work is for a bank from the Bank master; audit and internal
    # valuations name their client organisation as text instead.
    bank = models.ForeignKey("banks.Bank", on_delete=models.PROTECT, related_name="jobs", null=True, blank=True)
    client_name = models.CharField(max_length=255, blank=True)
    billing_address = models.TextField(blank=True)
    purpose = models.CharField(max_length=30, choices=PURPOSE_CHOICES, default="mortgage_security")

    property = models.ForeignKey(Property, on_delete=models.PROTECT, related_name="jobs")
    contact_for_access = models.CharField(max_length=255, blank=True)
    contact_name = models.CharField(max_length=255, blank=True)
    contact_number = models.CharField(max_length=50, blank=True)

    # Conflict of interest (CRM feedback LG-01): "yes" / "no", confirmed by
    # someone on Setup. Yes needs the consent (proof) uploaded as a document.
    coi_check = models.CharField(max_length=5, blank=True, default="")
    coi_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    coi_confirmed_at = models.DateTimeField(null=True, blank=True)

    # Fields ("tab.field") the valuer left out of the report in the
    # include-in-report step after the Inspection stage.
    report_exclusions = models.JSONField(default=list, blank=True)

    report_template = models.ForeignKey(
        "reports.ReportTemplate", null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs"
    )

    # Roles (CLAUDE.md §3)
    admin_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs_administered"
    )
    inspected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs_inspected"
    )
    valuer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs_valued"
    )
    registered_valuer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="jobs_signed", help_text="The signing valuer named on the report."
    )
    peer_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs_peer_reviewed"
    )
    counter_signatory = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="jobs_countersigned"
    )

    status = models.CharField(max_length=30, choices=JobStatus.CHOICES, default=JobStatus.INSTRUCTION_RECEIVED)
    version = models.PositiveIntegerField(default=1)
    parent_job = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reissues"
    )
    is_locked = models.BooleanField(default=False, help_text="Set True on issue; any edit must create a new version.")

    peer_review_comments = models.TextField(blank=True)

    # The second signature itself, not just who is assigned to give it
    # (CLAUDE.md §3). Cleared whenever the job goes back for changes.
    countersigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    countersigned_at = models.DateTimeField(null=True, blank=True)

    # Issuing renders the final PDF in a background task (apps.reports.tasks).
    # While one is queued or running the job takes no other moves.
    issue_requested_at = models.DateTimeField(null=True, blank=True)
    issue_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    issue_error = models.TextField(blank=True, help_text="Why the last issue attempt failed, if it did.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    inspection_scheduled_at = models.DateTimeField(null=True, blank=True)
    inspected_at = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.bayut_internal_reference_no} ({self.property})"

    def clean(self):
        """Surfaces the lock/transition rules as form errors in the admin.
        `save()` re-checks them so non-form writers can't bypass them."""
        super().clean()
        try:
            self._assert_write_allowed()
        except JobLockedError as exc:
            raise DjangoValidationError(str(exc)) from exc
        except TransitionError as exc:
            raise DjangoValidationError({"status": str(exc)}) from exc

    REFERENCE_ALLOCATION_ATTEMPTS = 5

    def save(self, *args, **kwargs):
        if self.bayut_internal_reference_no:
            self._assert_write_allowed()
            return super().save(*args, **kwargs)

        # New job: allocate a reference, retrying if a concurrent create
        # claimed the same number. The unique constraint is the arbiter —
        # read-then-write alone would race.
        last_error = None
        for _ in range(self.REFERENCE_ALLOCATION_ATTEMPTS):
            self.bayut_internal_reference_no = self._generate_reference_no()
            try:
                with transaction.atomic():
                    return super().save(*args, **kwargs)
            except IntegrityError as exc:
                if "bayut_internal_reference_no" not in str(exc):
                    raise
                last_error = exc
                self.bayut_internal_reference_no = ""
        raise last_error

    def _db_state(self):
        """The persisted row as it stands right now — what this save is
        about to change. Deliberately re-read per save rather than cached:
        the same instance is often saved several times in a row."""
        if not self.pk:
            return None
        return Job.all_objects.filter(pk=self.pk).only("status", "is_locked").first()

    def _assert_write_allowed(self):
        """The two rules from CLAUDE.md §3 that hold for every writer
        (API, admin, shell, Celery task), checked against one read."""
        db = self._db_state()
        if db is None:
            return
        if db.is_locked:
            raise JobLockedError(
                f"Job {self.bayut_internal_reference_no} is locked (issued) and cannot be "
                f"modified. Create a revision with create_revision() instead."
            )
        if db.status != self.status:
            validate_transition(db.status, self.status)

    def transition_to(self, new_status: str, *, comments: str = ""):
        """The only sanctioned way to move a job through its lifecycle."""
        validate_transition(self.status, new_status)
        self.status = new_status
        if new_status in (JobStatus.VALUATION_IN_PROGRESS, JobStatus.APPROVED_SIGNED):
            # A signature covers the numbers it was given on; any return for
            # changes (or a fresh approval) needs a new one.
            self.countersigned_by = None
            self.countersigned_at = None
        if new_status == JobStatus.INSPECTION_SCHEDULED:
            self.inspection_scheduled_at = timezone.now()
        if new_status == JobStatus.INSPECTED:
            self.inspected_at = timezone.now()
        if comments:
            self.peer_review_comments = comments
        self.save()
        return self

    def countersign(self, user):
        """Records the counter-signatory's signature on an approved job."""
        if self.status != JobStatus.APPROVED_SIGNED:
            raise TransitionError("Only an approved job can be counter-signed.")
        if user is None or user.pk != self.counter_signatory_id:
            raise TransitionError("Only the assigned counter-signatory can counter-sign.")
        self.countersigned_by = user
        self.countersigned_at = timezone.now()
        self.save()
        return self

    # `builtins.property`: inside this class `property` is the Property FK.
    @builtins.property
    def issue_in_progress(self) -> bool:
        """An issue is queued or running. A request older than the timeout is
        treated as lost (a worker that died), so the job isn't stuck forever."""
        if self.issue_requested_at is None:
            return False
        return timezone.now() - self.issue_requested_at < timezone.timedelta(
            seconds=settings.ISSUE_TASK_TIMEOUT_SECONDS
        )

    def issue(self):
        """Issues the report and locks the job. Refuses unless peer review,
        counter-signature and a valid RERA licence are all in place."""
        blockers = validate_issue_preconditions(self)
        if blockers:
            raise IssueBlockedError("; ".join(blockers))
        self.status = JobStatus.ISSUED
        self.issued_at = timezone.now()
        self.is_locked = True
        self.issue_requested_at = None
        self.issue_error = ""
        self.save()
        return self

    def coi_matches(self) -> list[tuple["Job", str]]:
        """Instructions in the last 12 months for the same property or
        applicant (CRM feedback LG-01), with what matched. This job's own
        versions don't count."""
        from datetime import timedelta

        from django.db.models import Q
        from django.utils import timezone

        prop = self.property
        rules = []
        unit, building = (prop.unit_number or "").strip(), (prop.building_name or "").strip()
        if unit and building:
            rules.append(("same unit and building",
                          Q(property__unit_number__iexact=unit, property__building_name__iexact=building)))
        plot, number = (prop.title_doc_plot_no or "").strip(), (prop.title_doc_property_no or "").strip()
        if plot and number:
            rules.append(("same plot and property number",
                          Q(property__title_doc_plot_no__iexact=plot, property__title_doc_property_no__iexact=number)))
        for name in prop.applicant_names:
            if len(name.strip()) >= 3:
                rules.append((f"same applicant ({name.strip()})", Q(property__applicant_name__icontains=name.strip())))
        if not rules:
            return []
        root = self.reference_root
        recent = (
            Job.objects.filter(created_at__gte=timezone.now() - timedelta(days=365))
            .exclude(pk=self.pk)
            .exclude(bayut_internal_reference_no__startswith=root)
            .exclude(property_id=self.property_id)
            .select_related("property")
            .order_by("-created_at")
        )
        found: dict[int, tuple[Job, str]] = {}
        for why, rule in rules:
            for job in recent.filter(rule)[:5]:
                found.setdefault(job.pk, (job, why))
        return list(found.values())[:5]

    @builtins.property
    def coi_suggestion(self) -> str:
        """What the COI check should probably say, for the person confirming it."""
        matches = self.coi_matches()
        if not matches:
            return "Suggested: No. No instruction for this property or applicant in the last 12 months."
        listed = "; ".join(
            f"{job.bayut_internal_reference_no} ({why}, {job.created_at:%d %b %Y})" for job, why in matches
        )
        return f"Suggested: Yes. Possible conflict: {listed}."

    @builtins.property
    def coi_confirmed(self) -> str:
        if not self.coi_confirmed_at:
            return ""
        from django.utils import timezone

        who = str(self.coi_confirmed_by) if self.coi_confirmed_by else "someone"
        return f"By {who}, {timezone.localtime(self.coi_confirmed_at):%d %b %Y %H:%M}"

    @builtins.property
    def map_link(self) -> str:
        """Google Maps at the property's coordinates, to navigate there (CRM
        feedback SC-02); no key needed for a link."""
        prop = self.property
        if prop.latitude is None or prop.longitude is None:
            return ""
        return f"https://www.google.com/maps/search/?api=1&query={prop.latitude},{prop.longitude}"

    @builtins.property
    def inspection_booked_at(self):
        """When the inspection was booked for, from the Scheduling stage."""
        scheduling = getattr(self, "scheduling", None)
        return scheduling.inspection_booked_at if scheduling else None

    @builtins.property
    def reference_root(self) -> str:
        """The reference of version 1. Every revision's reference is built on
        it, so the bank sees one Valuation Ref No. across re-issues."""
        job = self
        while job.parent_job_id:
            job = Job.all_objects.only("parent_job_id", "bayut_internal_reference_no").get(pk=job.parent_job_id)
        return job.bayut_internal_reference_no

    @builtins.property
    def file_stem(self) -> str:
        """Base name for this version's stored and downloaded files. Revisions
        already carry their version in the reference (`BYT-2026-00012-v2`)."""
        ref = self.bayut_internal_reference_no
        return ref if self.version > 1 else f"{ref}-v{self.version}"

    @builtins.property
    def organisation_name(self) -> str:
        """Who the report is for: the bank on mortgage work, otherwise the
        client organisation typed on the instruction."""
        if self.bank_id:
            return self.bank.name
        return self.client_name

    @builtins.property
    def bank_code(self) -> str:
        return self.bank.code if self.bank_id else ""

    TAB_DATA_RELATIONS = ("scheduling", "checklist", "summary", "inspection", "location", "valuation")

    @transaction.atomic
    def create_revision(self, *, by=None):
        """A re-issue keeps the old version and starts a new one
        (CLAUDE.md §3). The new version carries the old one's tab data
        forward so the valuer amends rather than re-keys."""
        source = Job.objects.get(pk=self.pk)

        revision = Job.objects.get(pk=self.pk)

        # Own copy of the property: the issued version's address must stay
        # exactly as signed while the revision's is amended.
        property_copy = Property.objects.get(pk=source.property_id)
        property_copy.pk = None
        property_copy._state.adding = True
        property_copy.save()

        revision.pk = None
        revision.property = property_copy
        revision.parent_job_id = source.pk
        revision.version = source.version + 1
        # Same reference as the version it replaces, with the version added,
        # so the bank can match the re-issue to its original instruction.
        revision.bayut_internal_reference_no = f"{source.reference_root}-v{revision.version}"
        revision.status = JobStatus.VALUATION_IN_PROGRESS
        revision.is_locked = False
        revision.issued_at = None
        revision.countersigned_by = None
        revision.countersigned_at = None
        revision.issue_requested_at = None
        revision.issue_requested_by = None
        revision.issue_error = ""
        revision.admin_user = by or source.admin_user
        revision.save()  # post_save creates the blank tab rows

        for relation in self.TAB_DATA_RELATIONS:
            src = getattr(source, relation, None)
            if src is None:
                continue
            dst = getattr(revision, relation)
            for field in src._meta.concrete_fields:
                if field.name in ("id", "job"):
                    continue
                setattr(dst, field.name, getattr(src, field.name))
            dst.save()

        # Photographs and documents carry forward too. The copies point at the
        # same stored files, which are never overwritten or removed.
        for relation in ("photos", "documents"):
            for item in getattr(source, relation).all():
                item.pk = None
                item._state.adding = True
                item.job = revision
                item.save()

        # The comparables the valuer chose carry forward with the rest of the
        # working. AVM runs don't: they are a record of what was suggested for
        # a particular version (CLAUDE.md §6), so the revision starts its own.
        from apps.evidence.models import JobComparable  # the evidence app depends on this one

        JobComparable.objects.bulk_create(
            JobComparable(job=revision, comparable_id=link.comparable_id, selected=link.selected, order=link.order)
            for link in JobComparable.objects.filter(job=source)
        )

        return revision

    def _generate_reference_no(self) -> str:
        year = timezone.now().year
        return f"BYT-{year}-{ReferenceCounter.next_for_year(year):05d}"


class JobTransition(models.Model):
    """One move through the lifecycle: who, from where to where, when, and
    what they said. Review comments live here (a return needs a reason), and
    it is the record turnaround metrics are measured from. The audit log
    already captures the status field changing; this adds the human context."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="transitions")
    from_status = models.CharField(max_length=30, choices=JobStatus.CHOICES)
    to_status = models.CharField(max_length=30, choices=JobStatus.CHOICES)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.job_id}: {self.from_status} -> {self.to_status}"


class JobTabVersion(models.Model):
    """Edit counter for one tab of one job, used for optimistic concurrency
    on the tab PATCH endpoint: a write names the version it was based on and
    is refused if someone else has saved since (first edit wins).

    Separate from the tab models because a tab can span several rows
    (Instructions is Job + Property), and per tab rather than per job
    because the inspector and valuer routinely work on different tabs of
    the same job at the same time."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="tab_versions")
    tab_key = models.CharField(max_length=40)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("job", "tab_key")]

    def __str__(self):
        return f"{self.job_id}:{self.tab_key}@{self.version}"


class JobTabData(models.Model):
    """Base for the per-tab models. Locking a job has to cover its tab data
    too — otherwise an issued report's valuation figures stay editable."""

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        job = Job.all_objects.filter(pk=self.job_id).only(
            "is_locked", "bayut_internal_reference_no"
        ).first()
        if job is not None and job.is_locked:
            raise JobLockedError(
                f"Job {job.bayut_internal_reference_no} is locked (issued); "
                f"{type(self).__name__} cannot be modified. Create a revision instead."
            )
        super().save(*args, **kwargs)


class SchedulingData(JobTabData):
    """Booking the inspection with the contact (CRM feedback SC-01..04)."""

    NOT_CALLED = "not_called"
    ANSWERED_NOT_SCHEDULED = "answered_not_scheduled"
    ANSWERED_SCHEDULED = "answered_scheduled"
    UNABLE_TO_CONTACT = "utc"
    CALL_STATUS_CHOICES = [
        (NOT_CALLED, "Not Called"),
        (ANSWERED_NOT_SCHEDULED, "Answered – Not Scheduled"),
        (ANSWERED_SCHEDULED, "Answered – Scheduled"),
        (UNABLE_TO_CONTACT, "UTC (Unable to contact)"),
    ]

    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="scheduling")
    call_status = models.CharField(max_length=30, choices=CALL_STATUS_CHOICES, default=NOT_CALLED)
    call_remark = models.TextField(blank=True)
    inspection_booked_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"SchedulingData<{self.job}>"


class CallAttempt(models.Model):
    """Every save on the Scheduling stage, so repeat UTC cases and earlier
    booked dates stay visible (CRM feedback SC-04)."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="call_attempts")
    status = models.CharField(max_length=30, choices=SchedulingData.CALL_STATUS_CHOICES)
    remark = models.TextField(blank=True)
    booked_for = models.DateTimeField(null=True, blank=True)
    by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                           related_name="+")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-at", "-id"]

    def __str__(self):
        return f"CallAttempt<{self.job_id} {self.status}>"


class ChecklistData(JobTabData):
    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="checklist")
    dld_location_checked = models.BooleanField(default=False)
    makani_photo = models.BooleanField(default=False)
    dewa_photo = models.BooleanField(default=False)
    newly_handed_over = models.BooleanField(default=False)
    satellite_measurement = models.BooleanField(null=True, blank=True)
    land_rate_applied = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    build_rate_applied = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"ChecklistData<{self.job}>"


class SummaryData(JobTabData):
    CAPACITY_CHOICES = [("external", "External"), ("internal", "Internal")]

    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="summary")
    interest_valued = models.CharField(max_length=60, blank=True)
    lease_expiry = models.DateField(null=True, blank=True)
    acquisition_method = models.CharField(max_length=30, blank=True)
    makani_number = models.CharField(max_length=50, blank=True)
    dewa_number = models.CharField(max_length=50, blank=True)
    information_provided = models.JSONField(default=list, blank=True)
    market_commentary = models.TextField(blank=True)
    property_floor_no = models.CharField(max_length=50, blank=True)
    floor_configuration = models.CharField(max_length=100, blank=True, help_text="e.g. B+G+2P+10")
    # Printed beside the floor in the report's Property Details; the free-text
    # configuration above can't be parsed into a number reliably.
    total_floors = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(200)], help_text="Floors in the building."
    )
    ground_elevation = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    no_of_bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    property_category = models.CharField(max_length=40, blank=True)
    type_of_property = models.CharField(max_length=100, blank=True)
    # Villas and townhouses: "Corner", "Single row" (CRM feedback IN-03).
    property_sub_type = models.CharField(max_length=100, blank=True)
    # yes / no / assumed (CRM feedback IN-02).
    parking = models.CharField(max_length=10, blank=True, default="")
    no_of_parkings = models.PositiveSmallIntegerField(null=True, blank=True)

    # Entered in sqm to 2 decimals (CRM feedback IN-01); sqft follows it and
    # is what the comparables, the AVM and the rate per sqft work in.
    bua_sqm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    bua_sqft = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    BUA_SOURCE_CHOICES = [
        ("title_deed", "Title Deed"),
        ("site_affection_plan", "Site Affection Plan"),
        ("initial_certificate_of_sale", "Initial Certificate of Sale"),
        ("spa", "SPA"),
        ("initial_contract_of_sale", "Initial Contract of Sale"),
        ("usufruct_certificate", "Usufruct Certificate"),
        ("floor_plan", "Floor Plan"),
        ("unit_plan", "Unit Plan"),
    ]
    bua_source = models.CharField(max_length=40, choices=BUA_SOURCE_CHOICES, blank=True)

    plot_area_sqft = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    plot_area_source = models.CharField(max_length=40, blank=True)

    # One of the standard statements (the `disclosure` presets), then edited.
    disclosure = models.TextField(blank=True)
    capacity_of_valuer = models.CharField(max_length=20, choices=CAPACITY_CHOICES, default="external")
    departures = models.TextField(default="None", blank=True)
    assumptions = models.TextField(blank=True)
    special_assumptions = models.JSONField(default=list, blank=True, help_text="[{title, body}]")
    other_matters = models.JSONField(default=list, blank=True, help_text="[{title, body}]")

    def save(self, *args, **kwargs):
        if self.bua_sqm is not None:
            self.bua_sqft = calculations.sqm_to_sqft_exact(self.bua_sqm)
        super().save(*args, **kwargs)

    @property
    def plot_area_sqm(self):
        if self.property_category not in PLOT_BEARING_CATEGORIES:
            return None
        return calculations.sqft_to_sqm(self.plot_area_sqft)

    @property
    def bua_requires_spa_caveat(self) -> bool:
        return self.bua_source == "spa"

    def __str__(self):
        return f"SummaryData<{self.job}>"


class InspectionData(JobTabData):
    # The dropdowns come from presets (seed_presets); these lists are what the
    # API accepts, so a new preset value needs adding here too.
    INSPECTION_TYPE_CHOICES = [
        ("full", "Full"), ("desktop", "Desktop"), ("drive_by", "Drive-by"),
        ("previous_inspection", "Previous inspection"), ("external_inspection", "External inspection"),
    ]
    UTILITY_STATUS_CHOICES = [
        ("connected", "Connected"), ("not_connected", "Not connected"), ("assumed_connected", "Assumed connected"),
    ]
    OCCUPANCY_CHOICES = [
        ("vacant", "Vacant"), ("owner_occupied", "Owner occupied"), ("tenanted", "Tenanted"),
        ("not_applicable", "Not applicable"), ("assumed_vacant", "Assumed vacant"),
        ("multi_tenanted", "Multi-tenanted"), ("tenanted_short_term", "Tenanted (short-term rental)"),
        ("under_construction", "Under construction"),
        ("not_applicable_under_construction", "Not applicable – under construction"),
    ]

    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="inspection")
    inspection_date = models.DateField(null=True, blank=True)
    inspection_type = models.CharField(max_length=20, choices=INSPECTION_TYPE_CHOICES, blank=True)
    service_charge = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                          help_text="Only for Abu Dhabi Islamic Bank.")
    roof = models.CharField(max_length=100, blank=True)
    external_walls = models.CharField(max_length=100, blank=True)
    structure = models.CharField(max_length=100, blank=True)
    flooring = models.JSONField(default=list, blank=True)
    walls = models.JSONField(default=list, blank=True)
    ceiling = models.JSONField(default=list, blank=True)
    lighting = models.JSONField(default=list, blank=True)
    electrical_services = models.CharField(max_length=20, choices=UTILITY_STATUS_CHOICES, blank=True)
    water = models.CharField(max_length=20, choices=UTILITY_STATUS_CHOICES, blank=True)
    sewerage = models.CharField(max_length=20, choices=UTILITY_STATUS_CHOICES, blank=True)
    air_conditioning = models.JSONField(default=list, blank=True)
    occupancy_title = models.CharField(max_length=40, blank=True, help_text="Floor, e.g. Ground, 1st, Mezzanine.")
    # Rooms on the ground floor (or in the unit), and on the first floor of
    # a villa or townhouse.
    accommodation_details = models.JSONField(default=list, blank=True)
    accommodation_first_floor = models.JSONField(default=list, blank=True)
    occupancy = models.CharField(max_length=40, choices=OCCUPANCY_CHOICES, blank=True)
    rent_if_any = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tenant_name = models.CharField(max_length=255, blank=True)
    tenancy_expiry = models.DateField(null=True, blank=True)
    sale_price_if_any = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    front_views = models.CharField(max_length=255, blank=True)
    rear_views = models.CharField(max_length=255, blank=True)
    upgraded = models.BooleanField(default=False)
    upgrade_comment = models.TextField(blank=True)
    repairs = models.TextField(blank=True, default=REPAIRS_DEFAULT)

    @property
    def views_summary(self):
        # Rear views apply to villas and townhouses only; one typed before the
        # category changed is not reported.
        summary = getattr(self.job, "summary", None) if self.job_id else None
        plot_bearing = getattr(summary, "property_category", None) in PLOT_BEARING_CATEGORIES
        return calculations.views_summary(self.front_views, self.rear_views if plot_bearing else "")

    @property
    def utilities_summary(self):
        return calculations.utilities_summary(self.electrical_services, self.water, self.sewerage)

    def __str__(self):
        return f"InspectionData<{self.job}>"


class LocationData(JobTabData):
    PROPERTY_STATUS_CHOICES = [("complete", "Complete"), ("under_construction", "Under Construction")]

    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="location")
    property_status = models.CharField(max_length=30, choices=PROPERTY_STATUS_CHOICES, blank=True)
    built_about = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Year.")
    built_date = models.DateField(null=True, blank=True)
    property_age_band = models.CharField(max_length=30, blank=True, help_text='e.g. "9 to 10"')
    developer = models.CharField(max_length=255, blank=True)
    coastline_distance_km = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Linear distance from the nearest coastline.",
    )
    # Typed in before it was calculated (see `remaining_economic_life`); kept
    # for the record, no longer entered or printed.
    remaining_economic_life_years = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(200)],
        help_text="Estimated remaining economic life of the building.",
    )
    sub_community = models.TextField(blank=True)
    location = models.TextField(blank=True)
    amenities = models.JSONField(default=list, blank=True)
    # The job's own editable copy of a library paragraph, not a short key.
    property_specification = models.TextField(blank=True)
    property_condition = models.TextField(blank=True)

    def _age_as_of(self):
        """As at the valuation date, so a report regenerated later still
        states the age it was valued at; today until one is entered."""
        valuation = getattr(self.job, "valuation", None) if self.job_id else None
        return getattr(valuation, "valuation_date", None)

    @property
    def exact_age(self) -> str:
        """'7 years, 7 months, 14 days' from the built date; whole years from
        the built year when no date is given (field dictionary)."""
        return calculations.age_text(self.built_date, self.built_about, as_of=self._age_as_of())

    @property
    def age_years(self):
        """Whole years, for the report's 'years' wording and the age band."""
        if self.built_date:
            return calculations.exact_age(self.built_date, as_of=self._age_as_of())
        return calculations.age_from_year(self.built_about, as_of=self._age_as_of())

    @property
    def remaining_economic_life(self):
        """45 years less the age at the valuation date, in whole years (CRM
        feedback VL-02); none until the built date or year is entered."""
        age = self.age_years
        if age is None:
            return None
        return max(ECONOMIC_LIFE_YEARS - int(age), 0)

    def __str__(self):
        return f"LocationData<{self.job}>"


def default_valuation_approaches():
    return ["market_approach_comparable_method"]


class ValuationData(JobTabData):
    BASIS_CHOICES = [
        ("market_value", "Market Value"),
        ("fair_value", "Fair Value"),
        ("market_rent", "Market Rent"),
        ("investment_value", "Investment Value"),
        ("market_value_transferable_title", "Market Value (Assuming Transferable Title)"),
    ]

    job = models.OneToOneField(Job, on_delete=models.CASCADE, related_name="valuation")
    valuation_date = models.DateField(null=True, blank=True)
    report_date = models.DateField(null=True, blank=True)
    basis_of_valuation = models.CharField(max_length=40, choices=BASIS_CHOICES, default="market_value")
    valuation_approach = models.CharField(max_length=255, default="Market approach – Comparable method")
    # The approaches used (presets `valuation_approach`); replaces the text above.
    valuation_approaches = models.JSONField(default=default_valuation_approaches, blank=True)
    valuation_commentary = models.TextField(blank=True)
    # Extra commentary by property type (CRM feedback VL-04); empty ones
    # aren't printed.
    commentary_villas = models.TextField(blank=True)
    commentary_offices = models.TextField(blank=True)
    commentary_retail = models.TextField(blank=True)
    market_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    # The report states one annual figure; the low/high range is no longer
    # entered but kept for jobs that have it.
    # One figure ("40,000") or a range ("30,000–50,000"), AED p.a. (CRM feedback VL-05).
    market_rent = models.CharField(max_length=40, blank=True, default="")
    market_rent_low = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    market_rent_high = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    forced_sale_discount_pct = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    reinstatement_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    reinstatement_note = models.TextField(blank=True)

    construction_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    completion_pct = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    land_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    as_is_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    assumed_complete_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    material_valuation_uncertainty = models.BooleanField(default=False)
    material_valuation_uncertainty_note = models.TextField(blank=True)

    @property
    def effective_forced_sale_discount_pct(self):
        from django.conf import settings

        if self.forced_sale_discount_pct is not None:
            return self.forced_sale_discount_pct
        bank_rules = getattr(self.job.bank, "rules", {}) or {}
        return bank_rules.get("forced_sale_discount_pct", settings.FORCED_SALE_DISCOUNT_PCT_DEFAULT)

    @property
    def forced_sale_value(self):
        return calculations.forced_sale_value(self.market_value, self.effective_forced_sale_discount_pct)

    @property
    def market_value_rate_per_sqft(self):
        bua_sqft = self.job.summary.bua_sqft if hasattr(self.job, "summary") else None
        return calculations.rate_per_sqft(self.market_value, bua_sqft)

    @property
    def market_value_in_words(self):
        return calculations.amount_in_words(self.market_value)

    def __str__(self):
        return f"ValuationData<{self.job}>"
