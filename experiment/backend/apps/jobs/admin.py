from django.contrib import admin

from .models import ChecklistData, InspectionData, Job, LocationData, Property, SummaryData, ValuationData


class ChecklistInline(admin.StackedInline):
    model = ChecklistData
    can_delete = False


class SummaryInline(admin.StackedInline):
    model = SummaryData
    can_delete = False


class InspectionInline(admin.StackedInline):
    model = InspectionData
    can_delete = False


class LocationInline(admin.StackedInline):
    model = LocationData
    can_delete = False


class ValuationInline(admin.StackedInline):
    model = ValuationData
    can_delete = False


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("bayut_internal_reference_no", "bank", "property", "status", "version", "is_locked", "created_at")
    list_filter = ("status", "bank", "purpose")
    search_fields = ("bayut_internal_reference_no", "bank_reference_no", "property__building_name")
    readonly_fields = ("bayut_internal_reference_no", "version", "is_locked", "created_at", "updated_at")
    inlines = [ChecklistInline, SummaryInline, InspectionInline, LocationInline, ValuationInline]

    def get_readonly_fields(self, request, obj=None):
        """An issued job is locked — show it, don't offer to edit it
        (the model refuses the write anyway)."""
        if obj is not None and obj.is_locked:
            return [f.name for f in self.model._meta.fields]
        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None):
        # 5-year retention (DLD 67/2020): issued jobs are never deleted.
        if obj is not None and obj.is_locked:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ("building_name", "unit_number", "community_name", "applicant_name")
    search_fields = ("building_name", "unit_number", "community_name", "applicant_name", "ownership_name")
