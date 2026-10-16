"""Shared domain keys.

These are the stable `PresetOption.value` keys that conditional-field
rules and model logic both key off. Kept in one place so a rule and the
calculation it guards can never drift apart.
"""

# Categories that sit on their own plot. Plot area, satellite measurement
# and reinstatement value apply only to these (CLAUDE.md §4 Tabs 1, 3, 6).
PLOT_BEARING_CATEGORIES = ("villa", "custom_villa", "townhouse")

# Occupancies with a tenancy: the report values subject to it, shows the rent,
# and the tenant's name and expiry apply.
TENANTED_OCCUPANCIES = ["tenanted", "multi_tenanted", "tenanted_short_term"]
