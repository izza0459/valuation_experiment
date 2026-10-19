from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CsrfView,
    FieldConfigView,
    JobActivityView,
    JobKpiView,
    JobReportFieldsView,
    JobReviseView,
    JobTabView,
    JobTransitionView,
    JobViewSet,
    OptionsView,
)

router = DefaultRouter()
router.register("jobs", JobViewSet, basename="job")

urlpatterns = [
    path("csrf/", CsrfView.as_view(), name="csrf"),
    path("field-config/", FieldConfigView.as_view(), name="field-config"),
    path("options/", OptionsView.as_view(), name="options"),
    # Before the router so it isn't captured as /jobs/<pk>/.
    path("jobs/kpis/", JobKpiView.as_view(), name="job-kpis"),
    path("jobs/<int:pk>/activity/", JobActivityView.as_view(), name="job-activity"),
    path("jobs/<int:pk>/revise/", JobReviseView.as_view(), name="job-revise"),
    path("jobs/<int:pk>/transitions/", JobTransitionView.as_view(), name="job-transitions"),
    path("jobs/<int:pk>/tabs/<str:tab>/", JobTabView.as_view(), name="job-tab"),
    path("jobs/<int:pk>/report-fields/", JobReportFieldsView.as_view(), name="job-report-fields"),
    path("", include(router.urls)),
]
