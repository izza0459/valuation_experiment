from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CsrfView,
    DashboardView,
    FieldConfigView,
    JobActivityView,
    JobCallView,
    JobFunnelView,
    JobKpiView,
    JobAssignView,
    JobLostView,
    JobSuggestionsView,
    JobSuggestionView,
    JobReportFieldsView,
    JobReviewerEditsView,
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
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("jobs/kpis/", JobKpiView.as_view(), name="job-kpis"),
    path("jobs/funnel/", JobFunnelView.as_view(), name="job-funnel"),
    path("jobs/<int:pk>/activity/", JobActivityView.as_view(), name="job-activity"),
    path("jobs/<int:pk>/lost/", JobLostView.as_view(), name="job-lost"),
    path("jobs/<int:pk>/assign/", JobAssignView.as_view(), name="job-assign"),
    path("jobs/<int:pk>/suggestions/", JobSuggestionsView.as_view(), name="job-suggestions"),
    path("jobs/<int:pk>/suggestions/<int:sid>/accept/", JobSuggestionView.as_view(action="accept"),
         name="job-suggestion-accept"),
    path("jobs/<int:pk>/suggestions/<int:sid>/decline/", JobSuggestionView.as_view(action="decline"),
         name="job-suggestion-decline"),
    path("jobs/<int:pk>/suggestions/<int:sid>/", JobSuggestionView.as_view(), name="job-suggestion"),
    path("jobs/<int:pk>/revise/", JobReviseView.as_view(), name="job-revise"),
    path("jobs/<int:pk>/transitions/", JobTransitionView.as_view(), name="job-transitions"),
    path("jobs/<int:pk>/tabs/<str:tab>/", JobTabView.as_view(), name="job-tab"),
    path("jobs/<int:pk>/report-fields/", JobReportFieldsView.as_view(), name="job-report-fields"),
    path("jobs/<int:pk>/calls/", JobCallView.as_view(), name="job-calls"),
    path("jobs/<int:pk>/reviewer-edits/accept/", JobReviewerEditsView.as_view(), name="job-reviewer-edits"),
    path("", include(router.urls)),
]
