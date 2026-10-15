from django.contrib import admin

from .models import ReportTemplate, ReportVersion


@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "bank", "active", "created_at")
    list_filter = ("active", "bank")
    search_fields = ("name", "version")


@admin.register(ReportVersion)
class ReportVersionAdmin(admin.ModelAdmin):
    list_display = ("job", "job_version", "template", "issued_at", "issued_by")
    readonly_fields = ("created_at",)
