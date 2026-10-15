"""Routes for the in-app Admin screens (design brief S8). Everything here is
admin-only; the viewsets enforce it."""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.accounts.admin_api import UserAdminViewSet
from apps.banks.api import BankViewSet
from apps.presets.api import PresetKeysView, PresetOptionViewSet, TextLibraryItemViewSet
from apps.reports.admin_api import ReportTemplateViewSet

router = SimpleRouter()
router.register("users", UserAdminViewSet, basename="admin-user")
router.register("banks", BankViewSet, basename="admin-bank")
router.register("presets", PresetOptionViewSet, basename="admin-preset")
router.register("library", TextLibraryItemViewSet, basename="admin-library")
router.register("templates", ReportTemplateViewSet, basename="admin-template")

urlpatterns = [
    path("preset-keys/", PresetKeysView.as_view(), name="admin-preset-keys"),
    path("", include(router.urls)),
]
