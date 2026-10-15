from django.urls import path

from .views import ReportPdfView, ReportPreviewView, ReportVersionsView

urlpatterns = [
    path("jobs/<int:pk>/report/preview/", ReportPreviewView.as_view(), name="report-preview"),
    path("jobs/<int:pk>/report/", ReportVersionsView.as_view(), name="report-versions"),
    path("jobs/<int:pk>/report/<int:version_id>/pdf/", ReportPdfView.as_view(), name="report-pdf"),
]
