"""Bank master administration (design brief S8)."""

from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import IsPlatformAdmin

from .models import Bank

# The rules the code actually reads. Anything else is a typo that would be
# silently ignored ("requires_service_chrage"), so unknown keys are refused.
BOOLEAN_RULES = {
    "requires_service_charge",
    "requires_makani_photo",
    "requires_dewa_photo",
    "requires_exact_age",
    "requires_forced_sale_value",
}
NUMERIC_RULES = {"forced_sale_discount_pct"}


class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = [
            "id", "name", "billing_address", "po_box", "contacts",
            "sla_signed", "sla_signed_date", "rules", "active",
        ]

    def validate_name(self, value):
        value = value.strip()
        clash = Bank.objects.filter(name__iexact=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A bank with this name already exists.")
        return value

    def validate_contacts(self, value):
        if not isinstance(value, list) or not all(isinstance(c, dict) for c in value):
            raise serializers.ValidationError("Contacts must be a list of {name, email, phone}.")
        allowed = {"name", "email", "phone"}
        for contact in value:
            if set(contact) - allowed or not all(isinstance(v, str) for v in contact.values()):
                raise serializers.ValidationError("Each contact may only have a name, email and phone (text).")
        return value

    def validate_rules(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Rules must be an object.")
        unknown = set(value) - BOOLEAN_RULES - NUMERIC_RULES
        if unknown:
            raise serializers.ValidationError(f"Unknown rule: {', '.join(sorted(unknown))}.")
        for key in BOOLEAN_RULES & set(value):
            if not isinstance(value[key], bool):
                raise serializers.ValidationError(f"{key} must be true or false.")
        pct = value.get("forced_sale_discount_pct")
        if pct is not None and (
            isinstance(pct, bool) or not isinstance(pct, int | float) or not 0 <= pct <= 100
        ):
            raise serializers.ValidationError("forced_sale_discount_pct must be a number from 0 to 100.")
        return value


class BankViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = BankSerializer
    queryset = Bank.objects.all()
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]  # banks are deactivated, not deleted
