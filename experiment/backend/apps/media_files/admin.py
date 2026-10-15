from django.contrib import admin

from .models import Document, Photo


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ("job", "caption", "order", "include_in_report")
    list_filter = ("include_in_report",)


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("job", "doc_type", "caption", "order", "include_in_report")
    list_filter = ("doc_type", "include_in_report")
