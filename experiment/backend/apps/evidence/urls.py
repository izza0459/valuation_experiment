from django.urls import path

from .views import AvmView, EvidenceItemView, EvidenceListView

urlpatterns = [
    path("jobs/<int:pk>/evidence/", EvidenceListView.as_view(), name="evidence-list"),
    path("jobs/<int:pk>/evidence/<int:link_id>/", EvidenceItemView.as_view(), name="evidence-item"),
    path("jobs/<int:pk>/avm/", AvmView.as_view(), name="avm"),
]
