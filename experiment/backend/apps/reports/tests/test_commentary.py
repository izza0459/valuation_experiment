"""The valuation commentary templates' blanks, filled for the report, and the
desktop valuation's report (no inspection date or photographs)."""
import datetime
from decimal import Decimal as D

import pytest
from django.core.management import call_command

from apps.banks.models import Bank
from apps.evidence.models import Comparable, JobComparable
from apps.jobs.models import Job, Property
from apps.presets import report_text
from apps.reports.commentary import Facts, fill, remaining_blanks
from apps.reports.context import build_context, unfilled_blanks

TEMPLATES = dict(report_text.VALUATION_COMMENTARY)

FACTS = Facts(
    beds=3, bua_sqft=D("3217.01"), plot_sqft=D("4500"), floor="G", views="Park view", building="Hayat 3",
    community="Dubai South", category="villa", occupancy="vacant", valuation_date="05 Nov 2026",
    market_value=D("3200000"), rate_per_sqft=D("994.71"),
    comparables=[("asking", D("3228199"), D("1003.5")), ("asking", D("3400000"), D("1050")),
                 ("sold", D("3000000"), D("950")), ("sold_primary", D("3150000"), D("980"))],
)


class TestFill:
    def test_a_villa_template_is_filled_from_the_comparables_and_the_job(self):
        text = fill(TEMPLATES["Villas/Townhouses"], FACTS)
        assert remaining_blanks(text) == []
        assert "3-bedroom villas in Dubai South are listed from AED 3,228,199 to AED 3,400,000" in text
        assert "transactions indicate AED 3,000,000 to AED 3,150,000 (AED 950 to AED 980 per sq ft)" in text
        # The brokers: listings above the dearest asking; offers around the value.
        assert "listings above AED 3,400,000" in text and "offers of around AED 3,200,000" in text
        assert "(3-bedroom, 3,217 sq ft BUA, 4,500 sq ft plot, Park view, standard specification)" in text
        assert text.endswith("as at 05 Nov 2026 is AED 3,200,000 (Three Million Two Hundred Thousand UAE Dirhams).")

    def test_an_apartment_template_is_filled(self):
        facts = Facts(**{**FACTS.__dict__, "category": "apartment", "floor": "23", "plot_sqft": None,
                         "building": "Marina Gate 1"})
        text = fill(TEMPLATES["Apartments"], facts)
        assert remaining_blanks(text) == []
        assert "apartments in Marina Gate 1" in text and "23rd floor, Park view" in text

    def test_an_office_uses_rates_rent_and_yield(self):
        facts = Facts(**{**FACTS.__dict__, "category": "fitted_office", "floor": "12", "plot_sqft": None,
                         "occupancy": "tenanted", "parkings": 2, "rent_low": D("240000"), "rent_high": D("260000")})
        text = fill(TEMPLATES["Shell and Core/Fitted Offices"], facts)
        assert remaining_blanks(text) == []
        assert "listed from AED 1,004 to AED 1,050 per sq ft" in text
        assert "net initial yield of 7.8%" in text and "2 parking spaces, tenanted" in text
        assert "is AED 3,200,000 (AED 995 per sq ft)." in text

    def test_what_only_the_valuer_knows_is_left_and_reported(self):
        text = fill(TEMPLATES["Shell and Core/Fitted Retail"], Facts(**{**FACTS.__dict__, "category": "fitted_retail"}))
        assert "[frontage/visibility]" in remaining_blanks(text)

    def test_nothing_known_leaves_the_template_as_it_was(self):
        assert fill(TEMPLATES["Apartments"], Facts()) == TEMPLATES["Apartments"]

    def test_the_cost_cross_check_goes_unless_both_figures_are_known(self):
        rare = TEMPLATES["Rare Property"]
        assert "cross-check" not in fill(rare, FACTS)
        with_costs = fill(rare, Facts(**{**FACTS.__dict__, "land_value": D("1000000"),
                                          "replacement_cost": D("2000000")}))
        assert "comprising land value of AED 1,000,000 plus depreciated replacement cost of AED 2,000,000." \
            in with_costs and "[As a cross-check" not in with_costs

    def test_text_the_valuer_wrote_is_kept(self):
        assert fill("Written for this job.", FACTS) == "Written for this job."


@pytest.fixture
def job():
    call_command("seed_presets")
    j = Job.objects.create(
        bank=Bank.objects.create(name="Test Bank"),
        property=Property.objects.create(unit_number="7", building_name="Hayat 3", community_name="Dubai South",
                                         applicant_name="A. Applicant"),
    )
    j.summary.property_category = "villa"
    j.summary.no_of_bedrooms = 3
    j.summary.bua_sqft = "3217.01"
    j.summary.save()
    j.valuation.market_value = "3200000"
    j.valuation.valuation_date = datetime.date(2026, 11, 5)
    j.valuation.valuation_commentary = TEMPLATES["Villas/Townhouses"]
    j.valuation.save()
    for status, price in (("asking", "3228199"), ("sold", "3000000")):
        c = Comparable.objects.create(source="manual", price_aed=price, bua_sqft="3217.01", status=status)
        JobComparable.objects.create(job=j, comparable=c, selected=True)
    return Job.objects.get(pk=j.pk)


@pytest.mark.django_db
class TestReport:
    def test_the_report_prints_the_commentary_filled_in(self, job):
        text = build_context(job)["text"]["valuation_commentary"]
        assert "listed from AED 3,228,199 to AED 3,228,199" in text and "xxxxx-bedroom" not in text

    def test_blanks_left_stop_the_report_being_finalised(self, job):
        # No views or plot recorded: those blanks stay, and are named.
        found = unfilled_blanks(build_context(job, issued=True))
        assert any(f.startswith("Valuation Commentary:") and "[position/view]" in f for f in found)

    def test_a_desktop_valuation_has_no_inspection_date_or_photographs(self, job):
        job.inspection.inspection_type = "desktop"
        job.inspection.inspection_date = datetime.date(2026, 11, 4)
        job.inspection.save()
        context = build_context(Job.objects.get(pk=job.pk))
        labels = {r["label"]: r["value"] for r in context["valuation_summary"]}
        assert "Date of inspection" not in labels and labels["Type of inspection"] == "Desktop"
        assert context["inspection_date"] == "" and context["desktop"] is True
        assert context["photos"] == [] and context["exec_photos"] == []

    def test_a_full_inspection_keeps_its_date(self, job):
        job.inspection.inspection_type = "full"
        job.inspection.inspection_date = datetime.date(2026, 11, 4)
        job.inspection.save()
        context = build_context(Job.objects.get(pk=job.pk))
        assert context["inspection_date"] == "04 Nov 2026" and context["desktop"] is False
