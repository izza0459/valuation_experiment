from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "changed_at", "model_name", "object_id", "field_name",
        "old_value", "new_value", "changed_by", "job",
    )
    list_filter = ("model_name",)
    search_fields = ("object_id", "field_name")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
