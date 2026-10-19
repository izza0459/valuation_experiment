from django.db import models


class Bank(models.Model):
    """Client master. Billing address auto-fills onto a Job's Instructions
    tab once sla_signed is True (CLAUDE.md §4 Tab 2)."""

    name = models.CharField(max_length=255)
    # The bank's own code, filled in on a job when the bank is picked.
    code = models.CharField(max_length=50, blank=True)
    billing_address = models.TextField(blank=True)
    po_box = models.CharField(max_length=50, blank=True)
    contacts = models.JSONField(default=list, blank=True, help_text="[{name, email, phone}]")
    sla_signed = models.BooleanField(default=False)
    sla_signed_date = models.DateField(null=True, blank=True)
    rules = models.JSONField(
        default=dict,
        blank=True,
        help_text="Bank-specific rules, e.g. "
        '{"requires_service_charge": true, "requires_makani_photo": true, '
        '"requires_dewa_photo": true, "requires_exact_age": true, '
        '"forced_sale_discount_pct": 15}',
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
