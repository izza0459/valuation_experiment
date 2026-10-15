"""Report template list for the admin screen (design brief S8). Templates are
authored in the Django admin; the app only lists versions and lets one be
switched off."""

from django.db.models import Count
from rest_framework import mixins, serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import IsPlatformAdmin

from .models import ReportTemplate


class ReportTemplateSerializer(serializers.ModelSerializer):
    bank_name = serializers.CharField(source="bank.name", default="", read_only=True)
    reports_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ReportTemplate
        fields = ["id", "name", "version", "bank", "bank_name", "active", "created_at", "reports_count"]
        read_only_fields = ["name", "version", "bank", "created_at"]


class ReportTemplateViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = ReportTemplateSerializer
    pagination_class = None
    http_method_names = ["get", "patch", "head", "options"]
    queryset = ReportTemplate.objects.select_related("bank").annotate(reports_count=Count("report_versions")).order_by(
        "name", "-created_at"
    )
