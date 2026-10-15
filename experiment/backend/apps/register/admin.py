from django.contrib import admin

from .models import ValuationRegisterEntry


@admin.register(ValuationRegisterEntry)
class ValuationRegisterEntryAdmin(admin.ModelAdmin):
    list_display = (
        "job", "requester_name", "property_type", "estimated_value",
        "valuation_date", "registered_with_dld",
    )
    list_filter = ("registered_with_dld", "property_type")
    search_fields = ("requester_name", "job__bayut_internal_reference_no")
