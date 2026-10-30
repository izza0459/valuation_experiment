from django.db import models


class PresetOption(models.Model):
    """Admin-editable dropdown option for a given tab field. Replaces
    hard-coded choices (CLAUDE.md §4: "all dropdown option lists are
    admin-editable presets"). `field_key` identifies which field/dropdown
    this option belongs to, e.g. "interest_valued", "roof", "flooring"."""

    field_key = models.CharField(max_length=100, db_index=True)
    value = models.SlugField(
        max_length=100,
        blank=True,  # auto-derived from the label on first save
        help_text="Stable key stored on the job and referenced by conditional-field "
        "rules (e.g. 'villa'). Renaming the label must not change this.",
    )
    label = models.CharField(max_length=255)
    report_text = models.TextField(
        blank=True, help_text="Preset paragraph inserted into the report when this option is picked."
    )
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    # Heading the option is listed under, as Bayut groups property types
    # (Residential / Commercial). Blank: not grouped.
    group = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["field_key", "order", "label"]
        unique_together = [("field_key", "value")]

    def __str__(self):
        return f"{self.field_key}: {self.label}"

    def _derive_value(self) -> str:
        from django.utils.text import slugify

        return slugify(self.label).replace("-", "_")

    def save(self, *args, **kwargs):
        if not self.value:
            self.value = self._derive_value()
        super().save(*args, **kwargs)


class TextLibraryCategory(models.TextChoices):
    ASSUMPTION = "assumption", "Assumption"
    SPECIAL_ASSUMPTION = "special_assumption", "Special Assumption"
    OTHER_MATTER = "other_matter", "Other Matter"
    CONDITION = "condition", "Property Condition"
    SPECIFICATION = "specification", "Property Specification"
    COMMENTARY = "commentary", "Market/Valuation Commentary (old)"
    MARKET_COMMENTARY = "market_commentary", "Market Commentary"
    VALUATION_COMMENTARY = "valuation_commentary", "Valuation Commentary"
    REINSTATEMENT = "reinstatement", "Reinstatement Cost"
    SPECIAL_NOTE = "special_note", "Special Note"


class TextLibraryItem(models.Model):
    """Admin-editable text library (CLAUDE.md §4 Tab 3/5/6). A job copies
    the body text onto its own tab data, then the valuer may edit it
    per-job without mutating the shared library entry."""

    category = models.CharField(max_length=30, choices=TextLibraryCategory.choices)
    title = models.CharField(max_length=255)
    body = models.TextField()
    # Property categories (preset values) this entry is offered for, e.g.
    # apartment commentary only for apartments. Empty: offered for all.
    property_categories = models.JSONField(default=list, blank=True)
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    # Deleted by an admin: hidden everywhere, and the dictionary sync never
    # brings it back. Kept as a row (soft delete, CLAUDE.md §7).
    deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ["category", "order", "title"]

    def __str__(self):
        return f"[{self.category}] {self.title}"
