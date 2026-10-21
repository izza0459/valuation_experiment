"""Shared domain keys.

These are the stable `PresetOption.value` keys that conditional-field
rules and model logic both key off. Kept in one place so a rule and the
calculation it guards can never drift apart.
"""

# Categories that sit on their own plot. Plot area, satellite measurement
# and reinstatement value apply only to these (CLAUDE.md §4 Tabs 1, 3, 6).
# A duplex follows the villa flow and fields (CRM feedback IN-06).
PLOT_BEARING_CATEGORIES = ("villa", "custom_villa", "townhouse", "duplex")

# Villas (and the like) are recorded storey by storey (CRM feedback IN-05):
# a basement if there is one, then the ground floor and up to five above it.
STOREYS = [
    ("basement", "Basement"), ("ground", "Ground floor"), ("first", "First floor"), ("second", "Second floor"),
    ("third", "Third floor"), ("fourth", "Fourth floor"), ("fifth", "Fifth floor"),
]
MAX_FLOORS_ABOVE_GROUND = 6


def storeys_for(floors_above_ground, has_basement) -> list[tuple[str, str]]:
    """The storeys a property has: `floors_above_ground` counts the ground
    floor (G+1 is 2)."""
    floors = max(1, min(int(floors_above_ground or 1), MAX_FLOORS_ABOVE_GROUND))
    above = [s for s in STOREYS if s[0] != "basement"][:floors]
    return ([STOREYS[0]] if has_basement else []) + above


# Parking that the report counts as present.
PARKING_PRESENT = ("yes", "assumed")

# Occupancies with a tenancy: the report values subject to it, shows the rent,
# and the tenant's name and expiry apply.
TENANTED_OCCUPANCIES = ["tenanted", "multi_tenanted", "tenanted_short_term"]

# Remaining economic life = this many years less the property's age at the
# valuation date (CRM feedback VL-02).
ECONOMIC_LIFE_YEARS = 45

# What the Repairs box starts with (CRM feedback IN-07); the valuer edits it.
REPAIRS_DEFAULT = (
    "No apparent repair or defects were noted in the visually accessible areas of the property at the time of "
    "inspection. This is not a structural or building survey, and no inaccessible or concealed areas were "
    "inspected. We cannot confirm the property is free from defects. The valuation assumes no material defects "
    "or repair liabilities exist beyond those noted, and we reserve the right to revise our opinion should any "
    "be identified."
)

# The reinstatement paragraph's blank for the figure: filled from the
# Reinstatement Value; a report can't be issued while it is still there.
FIGURE_BLANK = "[●]"
