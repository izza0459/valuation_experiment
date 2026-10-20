"""The report: what it prints, what it hides, how it is rendered safely and
how each version is kept (CLAUDE.md §5, §7)."""
import datetime
import json

import pytest
from django.core.management import call_command
from jinja2.exceptions import SecurityError, UndefinedError
from rest_framework.test import APIClient

from apps.accounts.models import User, ValuerProfile
from apps.banks.models import Bank
from apps.jobs.models import Job, Property
from apps.reports import render
from apps.reports.context import build_context
from apps.reports.generate import generate_report, render_version_html
from apps.reports.models import ReportTemplate, ReportVersion
from apps.reports.render import (
    DEFAULT_NAME,
    PdfEngineUnavailable,
    choose_template,
    ensure_default_template,
    pdf_engine_available,
    render_html,
)

pytestmark = pytest.mark.django_db

needs_pdf_engine = pytest.mark.skipif(
    not pdf_engine_available(), reason="WeasyPrint's system libraries aren't installed"
)


def make_user(name, **profile):
    user = User.objects.create(username=name, email=f"{name}@example.com", first_name=name.title())
    if profile:
        ValuerProfile.objects.create(user=user, **profile)
    return user


@pytest.fixture(autouse=True)
def presets():
    call_command("seed_presets")


@pytest.fixture
def dan():
    return make_user("dan", rera_registration_no="RERA-1", rics_membership_no="RICS-1",
                     qualifications="MRICS", title="Senior Valuer",
                     rera_licence_expiry=datetime.date(2099, 1, 1))


@pytest.fixture
def job(dan):
    j = Job.objects.create(
        bank=Bank.objects.create(name="Test Bank", billing_address="1 Bank St", po_box="123"),
        property=Property.objects.create(unit_number="312", building_name="Rukan Residences",
                                         community_name="Dubailand", applicant_name="A. Applicant"),
        valuer=dan, registered_valuer=dan, date_of_instruction=datetime.date(2026, 8, 26),
    )
    j.summary.property_category = "apartment"
    j.summary.interest_valued = "international_freehold"
    j.summary.bua_sqft = "519"
    j.summary.save()
    j.valuation.market_value = "725000"
    j.valuation.valuation_date = datetime.date(2026, 8, 26)
    j.valuation.save()
    return Job.objects.get(pk=j.pk)


def rows(ctx, section):
    return {r["label"]: r["value"] for r in ctx[section]}


# --- what is printed ---------------------------------------------------------------------------------


class TestContent:
    def test_the_snapshot_is_plain_json(self, job):
        """It is stored on the report version, so it must survive a round trip."""
        ctx = build_context(job)
        assert json.loads(json.dumps(ctx)) == ctx

    def test_preset_keys_become_the_labels_the_valuer_picked(self, job):
        assert rows(build_context(job), "property_details")["Interest valued"] == "International Freehold"

    def test_the_headline_figures(self, job):
        summary = rows(build_context(job), "valuation_summary")
        assert summary["Market Value"] == "AED 725,000"
        assert summary["Market Value in words"] == "Seven Hundred and Twenty-Five Thousand UAE Dirhams"
        assert summary["Market Value rate"] == "AED 1,397 / sqft"
        assert rows(build_context(job), "property_details")["Built-up area"] == "519 sqft (48 sqm)"

    def test_fractional_values_are_not_rounded_away(self, job):
        job.valuation.market_value = "725000.60"
        job.valuation.save()
        job.refresh_from_db()
        summary = rows(build_context(job), "valuation_summary")
        assert summary["Market Value"] == "AED 725,000.60"
        assert "and Sixty Fils" in summary["Market Value in words"]

    def test_plot_area_is_not_applicable_for_an_apartment_and_shown_for_a_villa(self, job):
        assert rows(build_context(job), "property_details")["Plot area"] == "Not Applicable"
        job.summary.property_category = "villa"
        job.summary.plot_area_sqft = "3229"
        job.summary.save()
        job.refresh_from_db()
        assert rows(build_context(job), "property_details")["Plot area"].startswith("3,229 sqft")

    def test_a_villa_without_a_plot_area_shows_a_dash_not_not_applicable(self, job):
        job.summary.property_category = "custom_villa"
        job.summary.save()
        job.refresh_from_db()
        assert rows(build_context(job), "property_details")["Plot area"] == "—"

    def test_lease_expiry_appears_only_for_a_long_leasehold(self, job):
        assert "Lease expiry" not in rows(build_context(job), "property_details")
        job.summary.interest_valued = "international_long_leasehold"
        job.summary.lease_expiry = datetime.date(2120, 1, 1)
        job.summary.save()
        job.refresh_from_db()
        assert rows(build_context(job), "property_details")["Lease expiry"] == "01 Jan 2120"

    def test_hidden_fields_stay_out_of_the_report_even_with_data(self, job):
        """Fields no longer on the form keep their data but aren't reported."""
        job.inspection.service_charge = "14.5"
        job.inspection.save()
        job.location.property_status = "under_construction"
        job.location.coastline_distance_km = "3"
        job.location.property_age_band = "9 to 10"
        job.location.save()
        job.valuation.as_is_value = "300000"
        job.valuation.market_rent_low, job.valuation.market_rent_high = "40000", "50000"
        job.valuation.save()
        job.bank.rules = {"requires_service_charge": True, "requires_forced_sale_value": True}
        job.bank.save()
        ctx = build_context(Job.objects.get(pk=job.pk))
        details, summary = rows(ctx, "property_details"), rows(ctx, "valuation_summary")
        for label in ("Service charge", "Distance from coastline", "Age band"):
            assert label not in details
        for label in ("Forced sale value", "Estimated rental range"):
            assert label not in summary
        assert "under_construction" not in ctx
        assert details["Year built"] == "Under construction"

    def test_the_report_template_rows(self, job):
        job.property.development = "The Views"
        job.property.save()
        job.summary.total_floors = 10
        job.summary.ground_elevation = "35"
        job.summary.no_of_bedrooms = 1
        job.summary.save()
        job.location.built_date = datetime.date(2019, 3, 1)
        job.location.save()
        job.valuation.market_rent = "60000"
        job.valuation.save()
        ctx = build_context(Job.objects.get(pk=job.pk))
        details, summary = rows(ctx, "property_details"), rows(ctx, "valuation_summary")
        assert "Rukan Residences, Dubailand" in details["Address (as inspected)"]
        assert details["Total no. of floors"] == "G + 10 Floors"
        assert details["Elevation above sea level"] == "Approximately 35 m"
        assert details["Type of property"] == "1 Bedroom apartment"
        assert details["Age of the property"] == "07.05"  # 1 Mar 2019 to 26 Aug 2026
        assert summary["Market Rent"] == "AED 60,000 per annum"

    def test_tenancy_and_reinstatement_wording(self, job):
        ctx = build_context(job)
        assert "part of a larger structure" in ctx["reinstatement"]  # an apartment
        assert ctx["tenancy"] == ""
        job.inspection.occupancy = "tenanted"
        job.inspection.rent_if_any = "90000"
        job.inspection.save()
        job.valuation.reinstatement_note = "Custom wording."
        job.valuation.save()
        ctx = build_context(Job.objects.get(pk=job.pk))
        assert ctx["tenancy"] == "The property is let at AED 90,000 per annum."  # no tenant name or expiry
        assert ctx["tenanted"] is True
        assert ctx["reinstatement"] == "Custom wording."

    def test_the_spa_caveat_appears_only_when_the_area_comes_from_an_spa(self, job):
        assert build_context(job)["bua_assumed_note"] == ""
        job.summary.bua_source = "spa"
        job.summary.save()
        job.refresh_from_db()
        assert "assumed to be correct" in build_context(job)["bua_assumed_note"]

    def test_upgrades_are_not_called_no_before_the_inspection_is_recorded(self, job):
        assert "Upgrades / modifications" in rows(build_context(job), "property_details")
        assert rows(build_context(job), "property_details")["Upgrades / modifications"] == "—"
        job.inspection.inspection_type = "full"
        job.inspection.save()
        job.refresh_from_db()
        assert rows(build_context(job), "property_details")["Upgrades / modifications"] == "No"

    def test_signatories_carry_their_registration_numbers(self, job, dan):
        valuer = build_context(job)["valuer"]
        assert (valuer["name"], valuer["title"], valuer["rera_no"], valuer["rics_no"]) == (
            "Dan", "Senior Valuer", "RERA-1", "RICS-1")
        assert build_context(job)["counter_signatory"] is None

    def test_a_signatory_without_a_profile_does_not_break_the_report(self, job):
        job.counter_signatory = make_user("bare")
        job.save()
        assert build_context(job)["counter_signatory"]["rera_no"] == ""

    def test_missing_values_show_a_dash_so_a_draft_makes_the_gap_obvious(self, job):
        assert rows(build_context(job), "property_details")["Developer"] == "—"

    def test_a_draft_lists_what_is_still_outstanding(self, job):
        meta = build_context(job)["meta"]
        assert meta["is_draft"] and any("Inspection" in item for item in meta["outstanding"])

    def test_an_issued_report_is_not_a_draft(self, job):
        Job.objects.filter(pk=job.pk).update(is_locked=True)
        job.refresh_from_db()
        meta = build_context(job)["meta"]
        assert meta["is_draft"] is False and meta["outstanding"] == []


# --- rendering ------------------------------------------------------------------------------------------


class TestRendering:
    def html(self, job):
        return render_html(choose_template(job), build_context(job))

    def test_it_renders_the_job(self, job):
        html = self.html(job)
        assert "AED 725,000" in html and "Rukan Residences" in html and "BYT-" in html

    def test_all_the_sections_of_the_spec_are_there(self, job):
        html = self.html(job)
        for heading in ("Executive Summary", "Terms of Engagement", "Extent of Due Diligence", "Property Analysis",
                        "Market Commentary", "Valuation Methodology", "Opinion of Market Value", "Disclaimer",
                        "Appendix 1", "Appendix 2", "Appendix 3", "Appendix 4", "Appendix 5"):
            assert heading in html, heading

    def test_the_firms_wording_is_in_the_report(self, job):
        """Terms of engagement, disclaimer and appendices carry the firm's
        template wording (Valuation_Report_Template.docx), not placeholders."""
        html = self.html(job)
        for words in (
            "neither the Valuer nor",  # independence
            "full disclosure of all information",  # disclaimer
            "Limitation of Liability",  # appendix 1
            "Ground Conditions",  # appendix 2
            "Fair Value (IFRS 13)",  # appendix 3
        ):
            assert words in html

    def test_an_unset_legal_name_is_visibly_a_placeholder(self, job, settings):
        settings.REPORT_FIRM_LEGAL_NAME = ""
        assert "[PLACEHOLDER – replace with approved wording: the firm’s registered legal name]" in self.html(job)

    def test_a_set_legal_name_leaves_no_placeholders(self, job, settings):
        settings.REPORT_FIRM_LEGAL_NAME = "Example Valuations LLC"
        html = self.html(job)
        assert "authorised by Example Valuations LLC" in html and "[PLACEHOLDER" not in html

    def test_the_opinion_names_the_tenancy_position(self, job):
        job.inspection.occupancy = "tenanted"
        job.inspection.save()
        assert "subject to the existing tenancy" in self.html(job)

    def test_hostile_text_in_job_data_cannot_inject_markup(self, job):
        job.property.applicant_name = '<script>alert("x")</script>'
        job.property.save()
        job.refresh_from_db()
        html = self.html(job)
        assert "<script>alert" not in html and "&lt;script&gt;" in html

    def test_a_firm_name_cannot_break_out_of_the_stylesheet(self, job, settings):
        settings.REPORT_FIRM_NAME = 'Evil"; } </style><script>alert(1)</script>'
        html = self.html(job)
        assert html.count("</style>") == 1 and "<script>alert(1)" not in html

    def test_a_stored_template_cannot_reach_python_internals(self, job):
        """Templates are typed in by admins and stored in the database."""
        template = ReportTemplate.objects.create(name="Evil", version="v1", html="{{ ''.__class__.__mro__ }}")
        with pytest.raises((SecurityError, UndefinedError)):
            render_html(template, build_context(job))

    def test_a_template_asking_for_something_the_report_lacks_fails_loudly(self, job):
        template = ReportTemplate.objects.create(name="Drift", version="v1", html="{{ not_a_real_key }}")
        with pytest.raises(UndefinedError):
            render_html(template, build_context(job))


# --- choosing a template -----------------------------------------------------------------------------------


class TestTemplateSelection:
    def test_the_shipped_default_is_stored_once(self):
        first, second = ensure_default_template(), ensure_default_template()
        assert first.pk == second.pk and first.name == DEFAULT_NAME

    def test_changing_the_shipped_files_makes_a_new_version_and_keeps_the_old(self, tmp_path, monkeypatch):
        old = ensure_default_template()
        (tmp_path / "report.html.j2").write_text("<p>changed</p>")
        (tmp_path / "report.css").write_text("")
        monkeypatch.setattr(render, "DEFAULT_DIR", tmp_path)
        new = ensure_default_template()
        assert new.pk != old.pk and new.version != old.version
        assert ReportTemplate.objects.filter(pk=old.pk).exists()

    def test_new_jobs_use_the_current_shipped_version_not_an_old_stored_copy(self, job, tmp_path, monkeypatch):
        old = choose_template(job)
        (tmp_path / "report.html.j2").write_text("<p>changed</p>")
        (tmp_path / "report.css").write_text("")
        monkeypatch.setattr(render, "DEFAULT_DIR", tmp_path)
        assert choose_template(job).pk != old.pk

    def test_a_template_chosen_on_the_job_wins(self, job):
        mine = ReportTemplate.objects.create(name="Mine", version="v1", html="x", css="")
        job.report_template = mine
        job.save()
        assert choose_template(job) == mine

    def test_an_inactive_choice_is_ignored(self, job):
        mine = ReportTemplate.objects.create(name="Mine", version="v1", html="x", css="", active=False)
        job.report_template = mine
        job.save()
        assert choose_template(job) != mine

    def test_a_bank_variant_beats_a_generic_one_which_beats_the_default(self, job):
        generic = ReportTemplate.objects.create(name="Generic", version="v1", html="x", css="")
        assert choose_template(job) == generic
        variant = ReportTemplate.objects.create(name="Bank", version="v1", html="x", css="", bank=job.bank)
        assert choose_template(job) == variant

    def test_another_banks_variant_is_not_used(self, job):
        other = Bank.objects.create(name="Other")
        ReportTemplate.objects.create(name="Theirs", version="v1", html="x", css="", bank=other)
        assert choose_template(job).name == DEFAULT_NAME


# --- keeping versions -------------------------------------------------------------------------------------------


class TestVersions:
    def stored(self, job):
        return ReportVersion.objects.create(
            job=job, job_version=job.version, template=choose_template(job), input_snapshot=build_context(job)
        )

    def test_a_stored_version_re_renders_from_its_snapshot_not_the_live_job(self, job):
        """So an issued report can always be reproduced exactly as signed."""
        version = self.stored(job)
        job.valuation.market_value = "999999"
        job.valuation.save()
        html = render_version_html(version)
        assert "AED 725,000" in html and "999,999" not in html

    def test_it_keeps_the_template_it_was_rendered_with(self, job):
        version = self.stored(job)
        assert version.template.version.startswith("v1-")

    @needs_pdf_engine
    def test_generating_stores_a_pdf_with_its_inputs(self, job, dan, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        version = generate_report(job, dan)
        assert version.job_version == job.version
        assert version.input_snapshot["meta"]["ref_no"] == job.bayut_internal_reference_no
        assert (tmp_path / version.pdf_s3_key).read_bytes().startswith(b"%PDF")

    @pytest.mark.skipif(pdf_engine_available(), reason="only meaningful without the engine")
    def test_without_the_pdf_engine_nothing_is_left_behind(self, job, dan):
        with pytest.raises(PdfEngineUnavailable):
            generate_report(job, dan)
        assert not ReportVersion.objects.exists()


# --- the API ---------------------------------------------------------------------------------------------


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class TestApi:
    def test_the_preview_is_html_for_a_participant(self, job, dan):
        res = client_for(dan).get(f"/api/jobs/{job.pk}/report/preview/")
        assert res.status_code == 200 and res["Content-Type"].startswith("text/html")
        assert "AED 725,000" in res.content.decode()
        assert "sandbox" in res["Content-Security-Policy"]

    def test_strangers_and_anonymous_users_cannot_see_it(self, job):
        assert client_for(make_user("stranger")).get(f"/api/jobs/{job.pk}/report/preview/").status_code == 404
        assert APIClient().get(f"/api/jobs/{job.pk}/report/preview/").status_code in (401, 403)

    def test_versions_are_listed_newest_first(self, job, dan):
        for _ in range(2):
            ReportVersion.objects.create(job=job, job_version=1, template=choose_template(job), input_snapshot={})
        res = client_for(dan).get(f"/api/jobs/{job.pk}/report/")
        assert res.status_code == 200 and len(res.json()) == 2 and res.json()[0]["is_draft"] is True

    @pytest.mark.skipif(pdf_engine_available(), reason="only meaningful without the engine")
    def test_generating_without_the_engine_says_so_plainly(self, job, dan):
        res = client_for(dan).post(f"/api/jobs/{job.pk}/report/")
        assert res.status_code == 503 and res.json()["code"] == "pdf_engine_unavailable"
        assert "pango" in res.json()["detail"].lower()
        assert not ReportVersion.objects.exists()

    def test_a_version_without_a_stored_pdf_is_a_404(self, job, dan):
        version = ReportVersion.objects.create(job=job, job_version=1, template=choose_template(job), input_snapshot={})
        assert client_for(dan).get(f"/api/jobs/{job.pk}/report/{version.pk}/pdf/").status_code == 404

    def test_a_version_cannot_be_fetched_through_another_job(self, job, dan):
        other = Job.objects.create(bank=job.bank, property=Property.objects.create(), valuer=dan)
        version = ReportVersion.objects.create(job=other, job_version=1, template=choose_template(job),
                                               input_snapshot={}, pdf_s3_key="reports/x.pdf")
        assert client_for(dan).get(f"/api/jobs/{job.pk}/report/{version.pk}/pdf/").status_code == 404

    def test_a_stored_pdf_is_served(self, job, dan, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        (tmp_path / "reports").mkdir()
        (tmp_path / "reports" / "x.pdf").write_bytes(b"%PDF-1.7 test")
        version = ReportVersion.objects.create(job=job, job_version=1, template=choose_template(job),
                                               input_snapshot={}, pdf_s3_key="reports/x.pdf")
        res = client_for(dan).get(f"/api/jobs/{job.pk}/report/{version.pk}/pdf/")
        assert res.status_code == 200 and res["Content-Type"] == "application/pdf"
        assert b"".join(res.streaming_content).startswith(b"%PDF")


class TestFieldDictionaryChanges:
    def test_a_villa_lists_each_floor_and_an_apartment_one(self, job):
        job.inspection.occupancy_title = ""
        job.inspection.accommodation_details = ["kitchen"]
        job.inspection.accommodation_first_floor = ["bedroom"]
        job.inspection.save()
        rooms = [row["floor"] for row in build_context(Job.objects.get(pk=job.pk))["accommodation"]]
        assert rooms == [""]  # apartment: first floor ignored
        job.summary.property_category = "villa"
        job.summary.save()
        rooms = [row["floor"] for row in build_context(Job.objects.get(pk=job.pk))["accommodation"]]
        assert rooms == ["Ground floor", "First floor"]

    def test_multi_selects_read_as_lists(self, job):
        job.inspection.air_conditioning = ["central", "district_cooling"]
        job.inspection.save()
        job.location.amenities = ["gym", "swimming_pool"]
        job.location.save()
        context = build_context(Job.objects.get(pk=job.pk))
        ac = rows(context, "building_specification")["Air conditioning"]
        assert ac == "Central Air Conditioning, District Cooling"
        assert context["text"]["amenities"] == "Gym, Swimming Pool"

    def test_the_report_address_is_the_title_document_one(self, job):
        prop = job.property
        prop.title_doc_property_no, prop.title_doc_plot_no = "312", "100"
        prop.title_doc_municipality_no, prop.title_doc_building_no = "123-1234", "1"
        prop.save()
        ctx = build_context(Job.objects.get(pk=job.pk))
        assert ctx["property"]["address"] == prop.address_as_per_document
        assert "Plot No. 100" in ctx["property"]["address"]

    def test_several_owners_and_applicants_are_listed(self, job):
        job.property.applicant_name = "A. One\nB. Two"
        job.property.ownership_name = "C. Owner"
        job.property.save()
        details = rows(build_context(Job.objects.get(pk=job.pk)), "property_details")
        assert details["Applicants"] == "A. One, B. Two"
        assert details["Owner"] == "C. Owner"

    def test_audit_work_is_for_the_named_client(self, job):
        Job.objects.filter(pk=job.pk).update(bank=None, purpose="audit_purpose", client_name="Acme Holdings")
        ctx = build_context(Job.objects.get(pk=job.pk))
        assert ctx["client"]["name"] == "Acme Holdings"
        assert rows(ctx, "property_details")["Client"] == "Acme Holdings"

    def test_fields_left_out_of_the_report_are_not_printed(self, job):
        job.inspection.air_conditioning = ["central"]
        job.inspection.save()
        Job.objects.filter(pk=job.pk).update(report_exclusions=["inspection.air_conditioning", "summary.bua_sqft"])
        ctx = build_context(Job.objects.get(pk=job.pk))
        assert "Air conditioning" not in rows(ctx, "building_specification")
        assert "Built-up area" not in rows(ctx, "property_details")

    def test_fields_up_to_valuation_can_be_left_out(self, job):
        job.location.developer = "Sobha Realty"
        job.location.save()
        Job.objects.filter(pk=job.pk).update(report_exclusions=["location.developer", "valuation.market_rent"])
        ctx = build_context(Job.objects.get(pk=job.pk))
        assert "Developer" not in rows(ctx, "property_details")
        assert "Market Rent" not in rows(ctx, "valuation_summary")

    def test_any_other_field_can_be_left_out_too(self, job):
        job.valuation.material_valuation_uncertainty = True
        job.valuation.save()
        job.inspection.repairs = "Cracked tile in the kitchen."
        job.inspection.save()
        Job.objects.filter(pk=job.pk).update(
            report_exclusions=["valuation.material_valuation_uncertainty", "inspection.repairs"])
        fresh = Job.objects.get(pk=job.pk)
        ctx = build_context(fresh)
        assert ctx["valuation"]["uncertainty"] is False and ctx["text"]["repairs"] == ""
        # Only the report leaves them out: the job keeps its values.
        assert fresh.valuation.material_valuation_uncertainty is True

    def test_what_a_bank_report_must_carry_cannot_be_left_out(self, job):
        from apps.jobs.field_config import REPORT_OPTIONAL
        assert "market_value" not in REPORT_OPTIONAL["valuation"]
        assert "applicant_name" not in REPORT_OPTIONAL["address"]

    def test_the_report_date_is_today_until_issued(self, job):
        job.valuation.report_date = None
        job.valuation.save()
        ctx = build_context(Job.objects.get(pk=job.pk))
        assert ctx["dates"]["report"] == datetime.date.today().strftime("%d %b %Y")
