from django.contrib import admin

from .models import PresetOption, TextLibraryItem


@admin.register(PresetOption)
class PresetOptionAdmin(admin.ModelAdmin):
    list_display = ("field_key", "label", "value", "order", "active")
    list_filter = ("field_key", "active")
    search_fields = ("field_key", "label", "value")
    ordering = ("field_key", "order")
    readonly_fields = ("value",)  # stable key: rules reference it, renaming the label must not break them


@admin.register(TextLibraryItem)
class TextLibraryItemAdmin(admin.ModelAdmin):
    list_display = ("category", "title", "order", "active")
    list_filter = ("category", "active")
    search_fields = ("title", "body")
