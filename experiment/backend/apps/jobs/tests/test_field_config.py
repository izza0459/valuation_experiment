"""The field config drives both the UI and (eventually) validation, so
its conditional rules must not depend on text an admin can edit."""
import pytest

from apps.jobs.constants import PLOT_BEARING_CATEGORIES
from apps.jobs.field_config import TABS, get_tab, serialize_config
from apps.presets.models import PresetOption

pytestmark = pytest.mark.django_db


def all_fields():
    for tab in TABS:
        for field in tab["fields"]:
            yield tab["key"], field


def find_field(tab_key, field_key):
    return next(f for f in get_tab(tab_key)["fields"] if f["key"] == field_key)


class TestStructure:
    def test_tabs_match_the_nine_in_the_spec(self):
        assert [tab["key"] for tab in serialize_config()] == [
            "checklist", "instructions", "summary", "inspection",
            "location", "valuation", "photos", "documents", "evidence",
        ]

    def test_every_field_key_is_unique_within_its_tab(self):
        for tab in TABS:
            keys = [f["key"] for f in tab["fields"]]
            assert len(keys) == len(set(keys)), f"duplicate keys in {tab['key']}"


class TestConditionalRules:
    def test_service_charge_keys_off_the_bank_master_not_a_bank_name(self):
        """Regression: this matched the literal string 'Abu Dhabi Islamic
        Bank', so renaming the bank silently dropped the field."""
        rule = find_field("inspection", "service_charge")["visible_if"]
        assert rule["field"] == "bank.rules.requires_service_charge"
        assert rule["op"] == "is_true"

    @pytest.mark.parametrize(
        "tab_key,field_key",
        [
            ("checklist", "satellite_measurement"),
            ("summary", "plot_area_sqm"),
            # Regression: these two were left always-visible, so an apartment
            # showed a plot-area source and a calculated plot sqft.
            ("summary", "plot_area_sqft"),
            ("summary", "plot_area_source"),
            ("valuation", "reinstatement_value"),
        ],
    )
    def test_plot_rules_share_one_constant(self, tab_key, field_key):
        rule = find_field(tab_key, field_key)["visible_if"]
        assert rule["value"] == list(PLOT_BEARING_CATEGORIES)

    def test_every_rule_uses_a_supported_operator(self):
        for _, field in all_fields():
            rule = field["visible_if"]
            if rule:
                assert rule["op"] in {"eq", "in", "is_true"}, field["key"]


class TestPresetValues:
    def test_value_is_derived_from_the_label(self):
        option = PresetOption.objects.create(field_key="property_category", label="Town House")
        assert option.value == "town_house"

    def test_renaming_a_label_keeps_the_stable_value(self):
        """The whole point: visibility rules reference `value`, so an
        admin editing the display text must not break them."""
        option = PresetOption.objects.create(field_key="property_category", label="Villa")
        assert option.value == "villa"

        option.label = "Villa (detached)"
        option.save()
        option.refresh_from_db()

        assert option.value == "villa"
        assert option.value in PLOT_BEARING_CATEGORIES

    def test_explicit_value_is_respected(self):
        option = PresetOption.objects.create(
            field_key="property_category", value="townhouse", label="Townhouse / Terraced"
        )
        assert option.value == "townhouse"
