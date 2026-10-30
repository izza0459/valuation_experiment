"""Dropdown presets and the text library (design brief S8)."""

from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsPlatformAdmin
from apps.jobs.field_config import TABS

from .models import PresetOption, TextLibraryItem
from .options import LIBRARY_CATEGORIES, RECORD_KEYS


def preset_keys() -> list[dict]:
    """The dropdowns an admin can edit: every option list in the field config
    that is made of presets (banks, templates and the text library are
    managed elsewhere)."""
    seen: dict[str, dict] = {}
    for tab in TABS:
        for f in tab["fields"]:
            key = f["options_key"]
            if not key or key in RECORD_KEYS or key in LIBRARY_CATEGORIES:
                continue
            seen.setdefault(key, {"key": key, "label": f["label"], "tab": tab["label"]})
    counts = {}
    for row in PresetOption.objects.filter(active=True).values_list("field_key", flat=True):
        counts[row] = counts.get(row, 0) + 1
    return [{**item, "count": counts.get(item["key"], 0)} for item in seen.values()]


class PresetKeysView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        return Response(preset_keys())


class PresetOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PresetOption
        fields = ["id", "field_key", "value", "label", "report_text", "order", "active", "group"]
        # The value is the stable key rules and stored jobs refer to: it is
        # derived from the label once and never changes after that.
        read_only_fields = ["value"]

    def validate_field_key(self, value):
        if value not in {k["key"] for k in preset_keys()}:
            raise serializers.ValidationError("Not an editable dropdown.")
        return value

    def validate(self, attrs):
        if self.instance is not None and "field_key" in attrs and attrs["field_key"] != self.instance.field_key:
            raise serializers.ValidationError({"field_key": "An option can't move to another dropdown."})
        if self.instance is None:
            probe = PresetOption(field_key=attrs["field_key"], label=attrs["label"])
            probe_value = probe._derive_value()
            if PresetOption.objects.filter(field_key=attrs["field_key"], value=probe_value).exists():
                raise serializers.ValidationError({"label": "This dropdown already has an option like this."})
        return attrs


class PresetOptionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = PresetOptionSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]  # deactivate, don't delete: jobs refer to them

    def get_queryset(self):
        queryset = PresetOption.objects.all()
        if key := self.request.query_params.get("field_key"):
            queryset = queryset.filter(field_key=key)
        return queryset


class TextLibraryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = TextLibraryItem
        fields = ["id", "category", "title", "body", "order", "active", "property_categories"]

    def validate_title(self, value):
        return value.strip()

    def validate_property_categories(self, value):
        """Property types the entry is offered for; empty means all of them."""
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise serializers.ValidationError("Must be a list of property types.")
        return value


class TextLibraryItemViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = TextLibraryItemSerializer
    pagination_class = None
    # Jobs keep their own copy of the text, so an entry can be deleted.
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        queryset = TextLibraryItem.objects.filter(deleted=False)
        if category := self.request.query_params.get("category"):
            queryset = queryset.filter(category=category)
        return queryset

    def perform_destroy(self, instance):
        instance.deleted, instance.active = True, False
        instance.save(update_fields=["deleted", "active"])
