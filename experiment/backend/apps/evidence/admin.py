from django.contrib import admin

from .models import AVMRun, Comparable, JobComparable


@admin.register(Comparable)
class ComparableAdmin(admin.ModelAdmin):
    list_display = ("source", "community_name", "building_name", "bua_sqft", "price_aed", "status", "transaction_date")
    list_filter = ("source", "status")
    search_fields = ("community_name", "building_name", "source_ref")


@admin.register(JobComparable)
class JobComparableAdmin(admin.ModelAdmin):
    list_display = ("job", "comparable", "selected", "order")
    list_filter = ("selected",)


@admin.register(AVMRun)
class AVMRunAdmin(admin.ModelAdmin):
    list_display = ("job", "job_version", "suggested_value", "low_value", "high_value", "confidence", "created_at")
    list_filter = ("confidence",)
    readonly_fields = ("created_at",)
