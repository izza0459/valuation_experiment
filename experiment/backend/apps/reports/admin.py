from django.contrib import admin

from .models import ReportDelivery, ReportTemplate, ReportVersion


@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "bank", "active", "created_at")
    list_filter = ("active", "bank")
    search_fields = ("name", "version")


@admin.register(ReportVersion)
class ReportVersionAdmin(admin.ModelAdmin):
    list_display = ("job", "job_version", "template", "issued_at", "issued_by")
    readonly_fields = ("created_at",)


@admin.register(ReportDelivery)
class ReportDeliveryAdmin(admin.ModelAdmin):
    list_display = ("job", "recipient_email", "status", "requested_by", "requested_at", "sent_at")
    list_filter = ("status",)
    readonly_fields = ("requested_at",)
