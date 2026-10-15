from django.contrib import admin

from .models import Bank


@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
    list_display = ("name", "sla_signed", "sla_signed_date", "active")
    list_filter = ("sla_signed", "active")
    search_fields = ("name",)
