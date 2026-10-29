from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path

from apps.accounts.auth_views import AuthConfigView, GoogleLoginView, LoginView, LogoutView, MeView


def healthcheck(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", healthcheck),
    path("api/auth/me/", MeView.as_view(), name="auth-me"),
    path("api/auth/login/", LoginView.as_view(), name="auth-login"),
    path("api/auth/config/", AuthConfigView.as_view(), name="auth-config"),
    path("api/auth/google/", GoogleLoginView.as_view(), name="auth-google"),
    path("api/auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("api/admin/", include("config.admin_api")),
    path("api/", include("apps.jobs.urls")),
    path("api/", include("apps.reports.urls")),
    path("api/", include("apps.media_files.urls")),
    path("api/", include("apps.evidence.urls")),
]
