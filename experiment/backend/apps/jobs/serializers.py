from rest_framework import serializers

from .models import ChecklistData, InspectionData, Job, LocationData, Property, SummaryData, ValuationData


class PropertySerializer(serializers.ModelSerializer):
    gps_dms = serializers.ReadOnlyField()
    address_as_per_document = serializers.ReadOnlyField()

    class Meta:
        model = Property
        fields = "__all__"


class ChecklistDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChecklistData
        exclude = ["id", "job"]


class SummaryDataSerializer(serializers.ModelSerializer):
    bua_sqft = serializers.ReadOnlyField()
    plot_area_sqft = serializers.ReadOnlyField()

    class Meta:
        model = SummaryData
        exclude = ["id", "job"]


class InspectionDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = InspectionData
        exclude = ["id", "job"]


class LocationDataSerializer(serializers.ModelSerializer):
    exact_age = serializers.ReadOnlyField()

    class Meta:
        model = LocationData
        exclude = ["id", "job"]


class ValuationDataSerializer(serializers.ModelSerializer):
    forced_sale_value = serializers.ReadOnlyField()
    market_value_rate_per_sqft = serializers.ReadOnlyField()
    market_value_in_words = serializers.ReadOnlyField()

    class Meta:
        model = ValuationData
        exclude = ["id", "job"]


class JobListSerializer(serializers.ModelSerializer):
    """Backs the jobs dashboard table (design brief S1)."""

    # The bank on mortgage work, otherwise the client organisation.
    bank_name = serializers.CharField(source="organisation_name", read_only=True)
    property_label = serializers.CharField(source="property.__str__", read_only=True)
    property_type = serializers.CharField(source="summary.property_category", read_only=True, default="")
    valuer_name = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    # Status and sub-status for the dashboard: the stage the job is in and
    # the section being worked on (the first one not yet complete).
    progress = serializers.SerializerMethodField()
    # The inspector's list shows when each inspection is booked for.
    inspection_booked_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Job
        fields = [
            "id", "bayut_internal_reference_no", "bank_reference_no", "bank_name",
            "property_label", "property_type", "valuer_name", "purpose",
            "status", "status_label", "progress", "version", "is_locked",
            "date_time_request_received", "created_at", "updated_at", "inspection_booked_at",
        ]

    def get_progress(self, job) -> dict:
        from .tabs import job_progress

        return job_progress(job)

    def get_valuer_name(self, job) -> str:
        valuer = job.valuer or job.registered_valuer
        return str(valuer) if valuer else ""


class JobDetailSerializer(serializers.ModelSerializer):
    property = PropertySerializer(read_only=True)
    bank_name = serializers.CharField(source="organisation_name", read_only=True)
    bank_code = serializers.CharField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    # Names for the workspace header's assignee avatars (design brief S3).
    assignees = serializers.SerializerMethodField()
    # Conditional fields key off the bank master's rules rather than the
    # bank's name (e.g. the ADIB service charge) — see field_config.py.
    bank_rules = serializers.SerializerMethodField()
    # Per-tab values, server-computed values, completion and edit version,
    # assembled by the same engine the PATCH endpoint uses (see tabs.py).
    tabs = serializers.SerializerMethodField()
    # What this user can do next and what blocks each move; the buttons are
    # drawn from this, so the UI never offers a move the server would refuse.
    available_actions = serializers.SerializerMethodField()
    # The signed-off PDF of an issued job, the revision made from it (if any),
    # and whether this user may make one.
    issued_report = serializers.SerializerMethodField()
    revision = serializers.SerializerMethodField()
    can_revise = serializers.SerializerMethodField()
    # Issuing runs in the background; the screen polls while this is true.
    issue_in_progress = serializers.BooleanField(read_only=True)
    countersigned_by_name = serializers.SerializerMethodField()
    # Review & Send tab: whether this user may send the issued report to the
    # bank, who at the bank it can go to, and where it has been sent.
    can_send_report = serializers.SerializerMethodField()
    bank_contacts = serializers.SerializerMethodField()
    deliveries = serializers.SerializerMethodField()
    # Every call made to book the inspection, newest first (CRM feedback SC-04).
    call_log = serializers.SerializerMethodField()
    checklist = ChecklistDataSerializer(read_only=True)
    summary = SummaryDataSerializer(read_only=True)
    inspection = InspectionDataSerializer(read_only=True)
    location = LocationDataSerializer(read_only=True)
    valuation = ValuationDataSerializer(read_only=True)

    class Meta:
        model = Job
        fields = "__all__"

    def get_call_log(self, job) -> list:
        return [
            {"id": c.id, "status": c.status, "status_label": c.get_status_display(), "remark": c.remark,
             "booked_for": c.booked_for, "by": str(c.by) if c.by else "", "at": c.at}
            for c in job.call_attempts.select_related("by")
        ]

    def get_bank_rules(self, job) -> dict:
        return (job.bank.rules if job.bank_id else None) or {}

    def get_tabs(self, job) -> dict:
        from .tabs import job_tab_state

        return job_tab_state(job, self.context["request"].user)

    def get_available_actions(self, job) -> list:
        from .transitions import available_actions

        return available_actions(job, self.context["request"].user)

    def get_can_send_report(self, job) -> bool:
        from apps.reports.delivery import may_send

        return job.is_locked and may_send(self.context["request"].user, job)

    def get_bank_contacts(self, job) -> list:
        from apps.reports.delivery import bank_contacts

        return bank_contacts(job)

    def get_deliveries(self, job) -> list:
        from apps.reports.delivery import describe_delivery

        return [describe_delivery(d) for d in job.deliveries.select_related("requested_by")]

    def get_countersigned_by_name(self, job):
        return str(job.countersigned_by) if job.countersigned_by_id else None

    def get_issued_report(self, job):
        version = job.report_versions.filter(issued_at__isnull=False).order_by("-issued_at").first()
        return {"id": version.id, "issued_at": version.issued_at} if version else None

    def get_revision(self, job):
        revision = job.reissues.order_by("-version").first()
        if revision is None:
            return None
        return {"id": revision.id, "reference": revision.bayut_internal_reference_no, "version": revision.version}

    def get_can_revise(self, job) -> bool:
        from apps.accounts.permissions import is_platform_admin

        return job.is_locked and is_platform_admin(self.context["request"].user) and not job.reissues.exists()

    def get_assignees(self, job) -> list:
        from apps.accounts.permissions import JOB_ROLE_FIELDS

        seen, people = set(), []
        for role, field in JOB_ROLE_FIELDS.items():
            user = getattr(job, field, None)
            if user is None:
                continue
            if user.id in seen:
                # One person commonly holds several roles on a job.
                next(p for p in people if p["id"] == user.id)["roles"].append(role)
                continue
            seen.add(user.id)
            people.append({"id": user.id, "name": str(user), "email": user.email, "roles": [role]})
        return people
