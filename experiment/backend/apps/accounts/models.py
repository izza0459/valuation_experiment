from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    """A user can hold several of these on a given job (CLAUDE.md §3)."""

    ADMIN = "admin", "Admin"
    # Takes instructions in and completes the Setup stage; the valuer does the rest.
    OPS = "ops", "Ops"
    INSPECTOR = "inspector", "Inspector"
    VALUER = "valuer", "Valuer"
    PEER_REVIEWER = "peer_reviewer", "Peer Reviewer"
    COUNTER_SIGNATORY = "counter_signatory", "Counter-signatory"


class User(AbstractUser):
    """Google Workspace SSO (OIDC) is the intended auth backend; the
    password-based fields stay for local/dev use until that's wired up."""

    email = models.EmailField(unique=True)
    roles = models.JSONField(
        default=list,
        blank=True,
        help_text="Default role set for this user (Role values). Actual "
        "per-job roles are assigned on the Job via explicit FKs.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.get_full_name() or self.email


class ValuerProfile(models.Model):
    """RICS/RERA credentials. Issue is blocked if licence_expiry has passed
    (CLAUDE.md §3, §7)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="valuer_profile")
    rera_registration_no = models.CharField(max_length=100, blank=True)
    rics_membership_no = models.CharField(max_length=100, blank=True)
    qualifications = models.CharField(max_length=255, blank=True, help_text="e.g. MRICS, BSc (Hons)")
    title = models.CharField(max_length=100, blank=True, help_text="e.g. Senior Valuer")
    rera_licence_expiry = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"ValuerProfile<{self.user}>"

    @property
    def is_licence_valid(self) -> bool:
        if not self.rera_licence_expiry:
            return False
        from django.utils import timezone

        return self.rera_licence_expiry >= timezone.localdate()
