"""Assumptions, Special Assumptions, Condition and Specification wording
("Valuation Report Text Inputs", Oct 2026)."""
import pytest
from django.core.management import call_command

from apps.jobs.models import Job
from apps.jobs.tests.test_tabs import bank, client_for, dan, job, patch
from apps.presets.dictionary import sync
from apps.presets.models import PresetOption, TextLibraryItem
from apps.reports.context import build_context, unfilled_blanks
from apps.reports.generate import preview_html

pytestmark = pytest.mark.django_db

__all__ = ["bank", "dan", "job"]


@pytest.fixture(autouse=True)
def library():
    call_command("seed_presets")
    sync(PresetOption, TextLibraryItem)


def library_body(category, title):
    return TextLibraryItem.objects.get(category=category, title=title, active=True).body


class TestLibrary:
    def test_the_documents_wording_is_loaded(self):
        titles = set(TextLibraryItem.objects.filter(category="assumption", active=True).values_list("title", flat=True))
        assert {"Vacant and Furnished", "Desktop Valuation", "Title Deed Error", "Custom"} <= titles
        assert len(titles) == 19  # 18 in the document, and Custom
        assert TextLibraryItem.objects.filter(category="special_assumption", active=True).count() == 5
        assert library_body("condition", "Previous Inspection") != library_body("specification", "Previous Inspection")


class TestReport:
    def test_the_opening_paragraphs_always_print(self, job, settings):
        settings.REPORT_FIRM_NAME = "Bayut Prime"
        html = preview_html(Job.objects.get(pk=job.pk))
        assert "Bayut Prime has relied on a number of assumptions" in html
        assert "A supposition taken to be true" in html
        assert "No Special Assumptions have been adopted." in html

    def test_yes_prints_the_chosen_paragraphs(self, job):
        job.summary.has_assumptions = True
        body = library_body("assumption", "Vacant and Furnished")
        job.summary.assumptions = [{"title": "Vacant and Furnished", "body": body}]
        job.summary.has_special_assumptions = True
        job.summary.special_assumptions = [{"title": "Custom", "body": "Assumed vacant possession on completion."}]
        job.summary.save()
        html = preview_html(Job.objects.get(pk=job.pk))
        assert "Vacant and Furnished" in html and "has adopted the following Special Assumptions" in html
        assert "Assumed vacant possession on completion." in html
        assert "<h4>Custom</h4>" not in html  # a custom paragraph prints without a heading

    def test_no_leaves_them_out(self, job):
        job.summary.has_assumptions = False
        job.summary.assumptions = [{"title": "Vacant and Furnished", "body": "x"}]
        job.summary.save()
        assert build_context(Job.objects.get(pk=job.pk))["text"]["assumptions"] == []

    def test_bullet_lines_print_as_bullets(self, job):
        job.location.property_condition = "Works required:\n- Repaint the hall\n- Fix the tap"
        job.location.save()
        assert "<ul><li>Repaint the hall</li><li>Fix the tap</li></ul>" in preview_html(Job.objects.get(pk=job.pk))


class TestBlanks:
    def test_unfilled_blanks_are_listed_and_stop_issue(self, job):
        from apps.reports.issue import issue_blockers

        job.summary.has_assumptions = True
        job.summary.assumptions = [{"title": "Drive By/External Inspection",
                                    "body": library_body("assumption", "Drive By/External Inspection")}]
        job.summary.save()
        found = unfilled_blanks(build_context(Job.objects.get(pk=job.pk)))
        assert found and "[date]" in found[0]
        assert any("Fill in the [blanks]" in b for b in issue_blockers(Job.objects.get(pk=job.pk)))

    def test_filled_in_text_passes(self, job):
        job.summary.has_assumptions = True
        job.summary.assumptions = [{"title": "Custom", "body": "Inspected on 21 October 2026."}]
        job.summary.save()
        assert unfilled_blanks(build_context(Job.objects.get(pk=job.pk))) == []


class TestTicked:
    def test_a_desktop_inspection_ticks_its_wording(self, job, dan):
        res = patch(client_for(dan), job, "inspection", {"inspection_type": "desktop"})
        assert res.status_code == 200, res.json()
        job = Job.objects.get(pk=job.pk)
        assert job.summary.has_assumptions
        assert [e["title"] for e in job.summary.assumptions] == ["Desktop Valuation"]
        good = library_body("condition", "Desktop Standard Property - Good Condition")
        assert job.location.property_condition == good
        assert job.location.property_specification == library_body("specification", "Desktop Standard Property")
        # The other sections' versions moved on, so a stale screen reloads.
        state = client_for(dan).get(f"/api/jobs/{job.pk}/").json()["tabs"]
        assert state["summary"]["version"] == 1 and state["location"]["version"] == 1

    def test_nothing_is_ticked_twice_or_over_a_choice(self, job, dan):
        job.location.property_condition = "Own wording."
        job.location.save()
        client = client_for(dan)
        patch(client, job, "inspection", {"inspection_type": "desktop"})
        patch(client, job, "inspection", {"inspection_type": "full"}, base_version=1)
        patch(client, job, "inspection", {"inspection_type": "desktop"}, base_version=2)
        job = Job.objects.get(pk=job.pk)
        assert len(job.summary.assumptions) == 1
        assert job.location.property_condition == "Own wording."

    def test_a_granted_title_ticks_the_special_assumption(self, job, dan):
        patch(client_for(dan), job, "summary", {"interest_valued": "gcc_freehold_granted"})
        job = Job.objects.get(pk=job.pk)
        assert job.summary.has_special_assumptions
        assert [e["title"] for e in job.summary.special_assumptions] == ["Granted"]


class TestOfferedFor:
    def test_options_are_offered_for_their_property_types(self):
        def offered(category, title):
            return TextLibraryItem.objects.get(category=category, title=title, active=True).property_categories

        assert offered("specification", "Shell and Core Office") == ["shell_core_office", "shell_core_retail"]
        assert offered("special_assumption", "Hotel Apartment") == ["apartment", "penthouse"]
        assert "villa" in offered("specification", "Custom Built Property")
        assert offered("assumption", "Desktop Valuation") == []  # every property type

    def test_a_desktop_office_gets_the_office_specification(self, job, dan):
        job.summary.property_category = "fitted_office"
        job.summary.save()
        patch(client_for(dan), job, "inspection", {"inspection_type": "desktop"})
        spec = Job.objects.get(pk=job.pk).location.property_specification
        assert spec == library_body("specification", "Desktop Fitted Office/Retail")
