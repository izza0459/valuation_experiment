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
    def test_tabs_match_the_spec(self):
        assert [tab["key"] for tab in serialize_config()] == [
            "instructions", "address", "scheduling", "checklist", "summary", "inspection", "photos",
            "location", "valuation", "documents", "evidence", "review",
        ]
        assert [tab["order"] for tab in TABS] == sorted(tab["order"] for tab in TABS)

    def test_every_tab_belongs_to_a_stage(self):
        from apps.jobs.field_config import STAGES

        stages = {s["key"] for s in STAGES}
        assert all(tab["stage"] in stages for tab in TABS)

    def test_a_stages_tabs_sit_together(self):
        """The workspace groups the tab bar by stage."""
        seen = []
        for tab in TABS:
            if not seen or seen[-1] != tab["stage"]:
                assert tab["stage"] not in seen, f"{tab['key']} splits the {tab['stage']} stage"
                seen.append(tab["stage"])

    def test_every_field_key_is_unique_within_its_tab(self):
        for tab in TABS:
            keys = [f["key"] for f in tab["fields"]]
            assert len(keys) == len(set(keys)), f"duplicate keys in {tab['key']}"


class TestConditionalRules:
    @pytest.mark.parametrize("tab_key,field_key", [
        ("checklist", "land_rate_applied"), ("instructions", "contact_for_access"),
        ("instructions", "report_template"), ("summary", "type_of_property"),
        ("inspection", "service_charge"), ("location", "coastline_distance_km"),
        ("location", "property_age_band"), ("valuation", "forced_sale_value"),
        ("valuation", "as_is_value"), ("valuation", "market_rent_low"),
    ])
    def test_fields_outside_the_sheet_and_report_are_hidden(self, tab_key, field_key):
        """Only what the field dictionary or the report template uses is on
        the form (the columns stay, so existing data is kept)."""
        assert field_key not in [f["key"] for f in get_tab(tab_key)["fields"]]

    def test_tenant_name_and_expiry_are_not_asked_for(self):
        keys = {f["key"] for f in get_tab("inspection")["fields"]}
        assert not keys & {"tenant_name", "tenancy_expiry"}

    @pytest.mark.parametrize(
        "tab_key,field_key",
        [
            ("checklist", "satellite_measurement"),
            ("summary", "plot_area_sqm"),
            ("inspection", "accommodation_by_storey"),
            ("inspection", "rear_views"),
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
                assert rule["op"] in {"eq", "in", "not_in", "is_true"}, field["key"]


class TestPresetValues:
    def test_value_is_derived_from_the_label(self):
        option = PresetOption.objects.create(field_key="property_category", label="Town House")
        assert option.value == "town_house"

    def test_renaming_a_label_keeps_the_stable_value(self):
        """The whole point: visibility rules reference `value`, so an
        admin editing the display text must not break them."""
        PresetOption.objects.filter(field_key="property_category").delete()  # seeded by migration
        option = PresetOption.objects.create(field_key="property_category", label="Villa")
        assert option.value == "villa"

        option.label = "Villa (detached)"
        option.save()
        option.refresh_from_db()

        assert option.value == "villa"
        assert option.value in PLOT_BEARING_CATEGORIES

    def test_explicit_value_is_respected(self):
        PresetOption.objects.filter(field_key="property_category").delete()  # seeded by migration
        option = PresetOption.objects.create(
            field_key="property_category", value="townhouse", label="Townhouse / Terraced"
        )
        assert option.value == "townhouse"
