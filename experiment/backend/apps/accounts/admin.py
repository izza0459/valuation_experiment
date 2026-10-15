from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, ValuerProfile


class ValuerProfileInline(admin.StackedInline):
    model = ValuerProfile
    can_delete = False


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = [ValuerProfileInline]
    list_display = ("email", "first_name", "last_name", "is_staff", "is_active")
    ordering = ("email",)
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Valuation platform", {"fields": ("roles",)}),
    )


@admin.register(ValuerProfile)
class ValuerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "rera_registration_no", "rics_membership_no", "rera_licence_expiry", "is_licence_valid")
    search_fields = ("user__email", "rera_registration_no", "rics_membership_no")
