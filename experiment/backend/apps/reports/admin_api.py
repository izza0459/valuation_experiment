"""Report template list for the admin screen (design brief S8). Templates are
authored in the Django admin; the app only lists versions and lets one be
switched off."""

from django.db.models import Count
from rest_framework import mixins, serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import IsPlatformAdmin

from .emails import MERGE_FIELDS
from .models import EmailTemplate, ReportTemplate


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


class EmailTemplateSerializer(serializers.ModelSerializer):
    bank_name = serializers.CharField(source="bank.name", default="", read_only=True)

    class Meta:
        model = EmailTemplate
        fields = ["id", "name", "bank", "bank_name", "subject", "body", "is_default", "active", "updated_at"]
        read_only_fields = ["updated_at"]

    def validate(self, attrs):
        bank = attrs.get("bank", getattr(self.instance, "bank", None))
        is_default = attrs.get("is_default", getattr(self.instance, "is_default", False))
        if is_default and bank is not None:
            raise serializers.ValidationError({"is_default": "The default template isn't for one bank."})
        return attrs

    def save(self, **kwargs):
        template = super().save(**kwargs)
        if template.is_default:
            EmailTemplate.objects.filter(is_default=True).exclude(pk=template.pk).update(is_default=False)
        return template


class EmailTemplateViewSet(viewsets.ModelViewSet):
    """Bank email templates. Not deleted: switched off (active=False)."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = EmailTemplateSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]
    queryset = EmailTemplate.objects.select_related("bank")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data = {"results": response.data, "merge_fields": MERGE_FIELDS}
        return response
