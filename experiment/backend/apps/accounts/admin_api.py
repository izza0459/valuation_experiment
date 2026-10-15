"""User administration (design brief S8: users, roles, valuer credentials).

Users are deactivated, never deleted: jobs, the audit trail and signed reports
refer to them. `is_staff` / `is_superuser` are deliberately not exposed: they
make someone a platform admin outside this app's role model, and an API that
could set them would let any admin mint a superuser.
"""

from __future__ import annotations

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Role, User, ValuerProfile
from .permissions import IsPlatformAdmin

# Warn this many days before a RERA licence runs out (design brief S8).
LICENCE_WARNING_DAYS = 60


def licence_state(profile) -> dict:
    expiry = getattr(profile, "rera_licence_expiry", None)
    if expiry is None:
        return {"state": "missing", "days_left": None}
    days = (expiry - timezone.localdate()).days
    if days < 0:
        return {"state": "expired", "days_left": days}
    return {"state": "expiring" if days <= LICENCE_WARNING_DAYS else "valid", "days_left": days}


class ValuerProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValuerProfile
        fields = ["rera_registration_no", "rics_membership_no", "qualifications", "title", "rera_licence_expiry"]


class UserAdminSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False)
    valuer_profile = ValuerProfileSerializer(required=False, allow_null=True)
    licence = serializers.SerializerMethodField()
    roles = serializers.ListField(child=serializers.ChoiceField(choices=Role.choices), required=False)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "name", "roles", "is_active",
            "password", "valuer_profile", "licence", "last_login",
        ]
        read_only_fields = ["last_login"]

    def get_name(self, user) -> str:
        return str(user)

    def get_licence(self, user) -> dict:
        return licence_state(getattr(user, "valuer_profile", None))

    # --- validation ---------------------------------------------------------

    def validate_email(self, value):
        value = value.strip().lower()
        clash = User.objects.filter(email__iexact=value)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate_roles(self, value):
        return list(dict.fromkeys(value))

    def validate_password(self, value):
        if value:
            try:
                validate_password(value)
            except DjangoValidationError as exc:
                raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate(self, attrs):
        me = self.context["request"].user
        if self.instance is not None and self.instance.pk == me.pk:
            # Locking yourself out would leave nobody able to undo it.
            if attrs.get("is_active") is False:
                raise serializers.ValidationError({"is_active": "You can't deactivate your own account."})
            if "roles" in attrs and Role.ADMIN not in attrs["roles"] and not (me.is_staff or me.is_superuser):
                raise serializers.ValidationError({"roles": "You can't remove your own admin role."})
        return attrs

    # --- writes ---------------------------------------------------------------

    def _save_profile(self, user, profile):
        if profile:
            ValuerProfile.objects.update_or_create(user=user, defaults=profile)

    def create(self, validated):
        profile = validated.pop("valuer_profile", None)
        password = validated.pop("password", "")
        user = User(username=validated["email"], **validated)
        # No password means the account can't sign in until one is set (SSO
        # will make this moot).
        user.set_password(password) if password else user.set_unusable_password()
        user.save()
        self._save_profile(user, profile)
        return user

    def update(self, user, validated):
        profile = validated.pop("valuer_profile", None)
        password = validated.pop("password", "")
        for attr, value in validated.items():
            setattr(user, attr, value)
        if "email" in validated:
            user.username = validated["email"]
        if password:
            user.set_password(password)
        user.save()
        self._save_profile(user, profile)
        return user


class UserAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = UserAdminSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch", "head", "options"]  # no delete: deactivate instead

    def get_queryset(self):
        queryset = User.objects.select_related("valuer_profile").order_by("first_name", "last_name", "email")
        if search := self.request.query_params.get("q"):
            queryset = queryset.filter(email__icontains=search) | queryset.filter(first_name__icontains=search)
        return queryset
