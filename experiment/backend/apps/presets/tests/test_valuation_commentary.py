"""Valuation commentary templates (Nov 2026): one per property type."""
import pytest
from django.core.management import call_command

from apps.presets.models import TextLibraryItem

pytestmark = pytest.mark.django_db

EXPECTED = {
    "apartment": "Apartments",
    "villa": "Villas/Townhouses",
    "townhouse": "Villas/Townhouses",
    "fitted_office": "Shell and Core/Fitted Offices",
    "shell_core_office": "Shell and Core/Fitted Offices",
    "fitted_retail": "Shell and Core/Fitted Retail",
    "shell_core_retail": "Shell and Core/Fitted Retail",
    "duplex": "Rare Property",
    "custom_villa": "Rare Property",
    "penthouse": "Rare Property",
}


def test_each_property_type_has_exactly_one_template():
    call_command("seed_presets")
    items = TextLibraryItem.objects.filter(category="valuation_commentary", active=True)
    for category, title in EXPECTED.items():
        tagged = [i.title for i in items if category in (i.property_categories or [])]
        assert tagged == [title], category
    assert items.filter(title="Custom").exists()
    assert all(i.body for i in items.exclude(title="Custom"))
