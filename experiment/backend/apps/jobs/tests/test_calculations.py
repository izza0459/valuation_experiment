"""Unit tests for the report/valuation maths (CLAUDE.md §2, §5).

These feed signed bank reports, so the edge cases matter more than the
happy path.
"""
import datetime
from datetime import date
from decimal import Decimal

import pytest

from apps.jobs import calculations as c


class TestAreaConversion:
    def test_sqm_to_sqft_uses_the_spec_factor(self):
        # CLAUDE.md §2: sqft = sqm × 10.76391
        # Rounded to whole numbers: no decimals on screen or in the report.
        assert c.sqm_to_sqft(Decimal("48.20")) == Decimal("519")

    def test_accepts_float_without_binary_noise(self):
        assert c.sqm_to_sqft(48.2) == Decimal("519")

    @pytest.mark.parametrize("empty", [None, ""])
    def test_missing_area_is_none(self, empty):
        assert c.sqm_to_sqft(empty) is None

    def test_format_area_matches_report_style(self):
        # Entered in sqft (field dictionary), sqm alongside.
        assert c.format_area(Decimal("519")) == "519 sqft (48 sqm)"
        assert c.format_area(Decimal("5381.95")) == "5,382 sqft (500 sqm)"

    def test_format_area_not_applicable_when_missing(self):
        assert c.format_area(None) == "Not Applicable"


class TestDMS:
    def test_converts_dubai_coordinates(self):
        # CLAUDE.md §4 Tab 2 worked example.
        assert c.decimal_to_dms(25.040306, is_lat=True) == "25°2'25.1\"N"

    def test_southern_and_western_hemispheres(self):
        assert c.decimal_to_dms(-25.040306, is_lat=True).endswith('"S')
        assert c.decimal_to_dms(-55.286231, is_lat=False).endswith('"W')

    def test_pair_formats_with_a_space(self):
        out = c.lat_long_to_dms(Decimal("25.040306"), Decimal("55.286231"))
        assert out == "25°2'25.1\"N 55°17'10.4\"E"

    def test_missing_coordinates_render_empty(self):
        assert c.lat_long_to_dms(None, Decimal("55.1")) == ""


class TestExactAge:
    def test_counts_whole_years(self):
        assert c.exact_age(datetime.date(2015, 1, 1), as_of=datetime.date(2026, 1, 1)) == 11

    def test_does_not_count_an_unreached_birthday(self):
        assert c.exact_age(datetime.date(2015, 12, 31), as_of=datetime.date(2026, 1, 1)) == 10

    def test_never_negative_for_a_future_build_date(self):
        assert c.exact_age(datetime.date(2030, 1, 1), as_of=datetime.date(2026, 1, 1)) == 0


class TestExactAgeText:
    def test_years_months_and_days_from_the_built_date(self):
        assert c.age_text(date(2019, 3, 1), None, as_of=date(2026, 10, 15)) == "7 years, 7 months, 14 days"

    def test_month_ends_are_clamped(self):
        assert c.age_text(date(2026, 1, 31), None, as_of=date(2026, 3, 1)) == "0 years, 1 month, 1 day"

    def test_the_built_year_gives_whole_years(self):
        assert c.age_text(None, 2015, as_of=date(2026, 10, 15)) == "11 years"

    def test_the_built_date_wins_over_the_year(self):
        assert c.age_text(date(2019, 3, 1), 2015, as_of=date(2026, 3, 1)) == "7 years, 0 months, 0 days"

    def test_nothing_entered_gives_nothing(self):
        assert c.age_text(None, None) == ""


class TestRatePerSqft:
    def test_divides_value_by_area(self):
        # Sample report quotes AED 1,397/sqft: whole dirhams.
        assert c.rate_per_sqft(Decimal("725000"), Decimal("519")) == Decimal("1397")

    def test_guards_against_divide_by_zero(self):
        assert c.rate_per_sqft(Decimal("725000"), Decimal("0")) is None


class TestForcedSaleValue:
    def test_applies_the_discount(self):
        assert c.forced_sale_value(Decimal("2500000"), Decimal("15")) == Decimal("2125000")

    def test_defaults_to_ten_percent_when_unset(self):
        assert c.forced_sale_value(Decimal("1000000"), None) == Decimal("900000")


class TestAmountInWords:
    def test_spec_example(self):
        # CLAUDE.md §5 worked example.
        assert (
            c.amount_in_words(725000)
            == "Seven Hundred and Twenty-Five Thousand UAE Dirhams"
        )

    def test_fractional_amount_does_not_contradict_the_figures(self):
        """Regression: this used to round to 725001 and render
        '...and One', so the words disagreed with the printed figure."""
        assert (
            c.amount_in_words(Decimal("725000.60"))
            == "Seven Hundred and Twenty-Five Thousand UAE Dirhams and Sixty Fils"
        )

    def test_singular_dirham(self):
        assert c.amount_in_words(1) == "One UAE Dirham"

    def test_zero(self):
        assert c.amount_in_words(0) == "Zero UAE Dirhams"

    def test_refuses_negative_rather_than_printing_minus(self):
        with pytest.raises(ValueError):
            c.amount_in_words(Decimal("-5000"))

    def test_none_renders_empty(self):
        assert c.amount_in_words(None) == ""


class TestAddressAsPerDocument:
    def test_builds_the_full_string(self):
        # CLAUDE.md §4 Tab 2 format.
        assert c.format_address_as_per_document(
            "1203", "55", "339", "1", "Marina Gate 1", "Dubai Marina"
        ) == (
            "Property No. 1203, Plot No. 55, Municipality No. 339, Building No. 1, "
            "Marina Gate 1, Dubai Marina, Dubai, United Arab Emirates"
        )

    def test_omits_blank_parts(self):
        out = c.format_address_as_per_document("", "", "", "", "Marina Gate 1", "Dubai Marina")
        assert out == "Marina Gate 1, Dubai Marina, Dubai, United Arab Emirates"


class TestViewsSummary:
    def test_states_front_and_rear(self):
        assert c.views_summary("Marina", "Road") == "Front: Marina; Rear: Road"

    def test_only_what_was_recorded(self):
        assert c.views_summary("Marina", "") == "Front: Marina"
        assert c.views_summary("", " Road ") == "Rear: Road"

    def test_nothing_recorded_says_nothing(self):
        assert c.views_summary("", "") == ""
        assert c.views_summary(None, None) == ""


class TestUtilitiesSummary:
    def test_all_the_same_reads_as_one_sentence(self):
        assert (
            c.utilities_summary("connected", "connected", "connected")
            == "Electricity, water and sewerage: connected."
        )

    def test_a_mixed_position_is_never_folded_into_a_blanket_claim(self):
        summary = c.utilities_summary("connected", "assumed_connected", "not_connected")
        assert summary == "Electricity: connected; Water: assumed connected; Sewerage: not connected."

    def test_assumed_is_not_reported_as_connected(self):
        summary = c.utilities_summary("assumed_connected", "assumed_connected", "assumed_connected")
        assert "assumed connected" in summary and "Electricity, water and sewerage: connected" not in summary

    def test_a_missing_status_is_called_out(self):
        summary = c.utilities_summary("connected", "connected", "")
        assert summary == "Electricity: connected; Water: connected; Sewerage: not recorded."

    def test_nothing_recorded_says_nothing(self):
        assert c.utilities_summary("", "", "") == ""
