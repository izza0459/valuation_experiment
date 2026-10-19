"""DLD sales as comparables."""
import gzip
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.banks.models import Bank
from apps.evidence import dld
from apps.evidence.models import Comparable, DldTransaction, JobComparable
from apps.jobs.models import Job, Property

pytestmark = pytest.mark.django_db

RECENT = (date.today() - timedelta(days=40)).isoformat()
OLD = (date.today() - timedelta(days=500)).isoformat()

# Dubai Pulse layout (made-up test rows).
PULSE = (
    "transaction_id,procedure_name_en,trans_group_en,instance_date,property_type_en,property_sub_type_en,"
    "property_usage_en,reg_type_en,area_name_en,building_name_en,project_name_en,master_project_en,rooms_en,"
    "procedure_area,actual_worth\n"
    f"T-1,Sell,Sales,{RECENT} 10:00:00,Unit,Flat,Residential,Existing Properties,Marsa Dubai,Test Tower A,"
    "Test Project,Dubai Marina,1 B/R,79.00,1500000\n"
    f"T-2,Sell,Sales,{RECENT} 11:00:00,Unit,Flat,Residential,Off-Plan Properties,Marsa Dubai,Test Tower B,"
    "Test Project,Dubai Marina,1 B/R,80.00,1600000\n"
    f"T-3,Sell,Sales,{OLD} 11:00:00,Unit,Flat,Residential,Existing Properties,Marsa Dubai,Test Tower A,"
    "Test Project,Dubai Marina,1 B/R,79.00,1200000\n"
    f"T-4,Lease,Mortgages,{RECENT} 11:00:00,Unit,Flat,Residential,Existing Properties,Marsa Dubai,Test Tower A,"
    "Test Project,Dubai Marina,1 B/R,79.00,900000\n"
    f"T-5,Sell,Sales,{RECENT} 12:00:00,Unit,Flat,Residential,Existing Properties,Marsa Dubai,Test Tower C,"
    "Test Project,Dubai Marina,Studio,40.00,700000\n"
    f"T-6,Sell,Sales,{RECENT} 12:00:00,Villa,Villa,Residential,Existing Properties,Wadi Al Safa 6,,"
    "Test Ranches,Arabian Ranches,4 B/R,400.00,6000000\n"
)

# The layout of the export on DLD's open-data page.
EXPORT = (
    "Transaction Number,Transaction Date,Transaction Type,Transaction sub type,Registration type,Usage,Area,"
    "Property Type,Property Sub Type,Amount,Property Size (sq.m),Room(s),Master Project,Project\n"
    f"E-1,{RECENT},Sales,Sell,Ready,Residential,MARSA DUBAI,Unit,Flat,1450000,78,1 B/R,Dubai Marina,Test Tower A\n"
)


# The open-data page's export as downloaded on 19 Oct 2026 (made-up rows).
OPEN_DATA = (
    "TRANSACTION_NUMBER,INSTANCE_DATE,GROUP_EN,PROCEDURE_EN,IS_OFFPLAN_EN,IS_FREE_HOLD_EN,USAGE_EN,AREA_EN,"
    "PROP_TYPE_EN,PROP_SB_TYPE_EN,TRANS_VALUE,PROCEDURE_AREA,ACTUAL_AREA,ROOMS_EN,PARKING,NEAREST_METRO_EN,"
    "NEAREST_MALL_EN,NEAREST_LANDMARK_EN,TOTAL_BUYER,TOTAL_SELLER,MASTER_PROJECT_EN,PROJECT_EN\n"
    f'"O-1","{RECENT} 16:00:21","Sales","Sale","Ready","Free Hold","Residential","MARSA DUBAI","Unit","Flat",'
    '"1450000","78.50","78.50","1 B/R","1","","","","1","1","Dubai Marina","TEST TOWER A"\n'
    f'"O-2","{RECENT} 16:00:21","Mortgage","Mortgage Registration","Ready","Free Hold","Residential",'
    '"MARSA DUBAI","Unit","Flat","900000","78.50","78.50","1 B/R","1","","","","0","0","Dubai Marina","TEST TOWER A"\n'
)


def load(text):
    return dld.import_file(io.BytesIO(text.encode()))


@pytest.fixture
def dan():
    return User.objects.create(username="dan", email="dan@example.com", first_name="Dan")


@pytest.fixture
def job(dan):
    j = Job.objects.create(
        bank=Bank.objects.create(name="Bank"),
        property=Property.objects.create(building_name="Test Tower A", community_name="Dubai Marina"),
        valuer=dan,
    )
    j.summary.property_category = "apartment"
    j.summary.no_of_bedrooms = 1
    j.summary.bua_sqft = Decimal("850")
    j.summary.save()
    return Job.objects.get(pk=j.pk)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


class TestImport:
    def test_loads_sales_only_and_reads_both_layouts(self):
        result = load(PULSE)
        assert result == {"rows": 6, "added": 5, "skipped": 1, "already_loaded": 0}  # the mortgage is skipped
        t = DldTransaction.objects.get(transaction_number="T-2")
        assert (t.beds, t.is_offplan, t.size_sqm, t.price_aed) == (1, True, Decimal("80.00"), Decimal("1600000"))
        assert DldTransaction.objects.get(transaction_number="T-5").beds == 0  # studio
        load(EXPORT)
        e = DldTransaction.objects.get(transaction_number="E-1")
        assert (e.area_name, e.project_name, e.is_offplan) == ("MARSA DUBAI", "Test Tower A", False)

    def test_loading_again_adds_nothing(self):
        load(PULSE)
        assert load(PULSE)["added"] == 0 and DldTransaction.objects.count() == 5

    def test_reads_the_open_data_export(self):
        assert load(OPEN_DATA)["added"] == 1  # the mortgage is left out
        t = DldTransaction.objects.get(transaction_number="O-1")
        assert (t.project_name, t.master_project, t.is_offplan, t.beds) == ("TEST TOWER A", "Dubai Marina", False, 1)

    def test_the_deploy_loads_a_gzipped_file_once(self, tmp_path):
        path = tmp_path / "transactions.csv.gz"
        path.write_bytes(gzip.compress(OPEN_DATA.encode()))
        call_command("import_dld", str(path), "--if-empty")
        assert DldTransaction.objects.count() == 1
        DldTransaction.objects.all().update(price_aed=1)
        call_command("import_dld", str(path), "--if-empty")  # already loaded: untouched
        assert DldTransaction.objects.get().price_aed == 1

    def test_a_file_that_isnt_dld_is_refused(self):
        with pytest.raises(dld.DldFileError):
            load("name,price\nx,1\n")


class TestSearch:
    def test_the_job_s_own_filters_find_the_right_sales(self, job):
        load(PULSE)
        params = dld.defaults_for(job)
        assert params["type"] == "apartment" and params["bua_min"] == "680" and params["bua_max"] == "1020"
        found = {t.transaction_number for t in dld.search(params)}
        # Not the off-plan one (the job is ready), the old one, the studio or the villa.
        assert found == {"T-1"}

    def test_the_community_matches_its_dld_area_name(self, job):
        load(EXPORT)
        params = {**dld.defaults_for(job), "building": ""}
        assert [t.transaction_number for t in dld.search(params)] == ["E-1"]  # "Dubai Marina" -> "Marsa Dubai"

    def test_filters_can_be_widened(self, job):
        load(PULSE)
        params = {**dld.defaults_for(job), "building": "", "status": "any", "months": 24}
        assert {t.transaction_number for t in dld.search(params)} == {"T-1", "T-2", "T-3"}


class TestMatching:
    def test_spacing_dashes_and_phase_numbers_are_ignored(self, job):
        load(PULSE)
        DldTransaction.objects.filter(transaction_number="T-1").update(area_name="DUBAI HEALTHCARE CITY - PHASE 2")
        params = {**dld.defaults_for(job), "community": "health care city 2", "building": ""}
        assert [t.transaction_number for t in dld.search(params)] == ["T-1"]

    def test_generic_words_in_a_building_name_are_dropped(self, job):
        load(PULSE)
        DldTransaction.objects.filter(transaction_number="T-1").update(project_name="RUKAN 3")
        params = {**dld.defaults_for(job), "building": "Rukan Residences"}
        assert [t.transaction_number for t in dld.search(params)] == ["T-1"]

    def test_an_empty_search_widens_and_says_how(self, job):
        load(PULSE)
        # No such building: the community's other sales are used instead,
        # widened further while fewer than ENOUGH turn up.
        found, widened = dld.search_widening({**dld.defaults_for(job), "building": "Nowhere Tower"})
        assert "T-1" in {t.transaction_number for t in found}
        assert widened and widened[0].startswith("any building")

    def test_the_same_building_elsewhere_comes_before_loosening(self, job):
        load(PULSE)
        params = {**dld.defaults_for(job), "community": "Somewhere Else", "building": "Test Tower A"}
        found, widened = dld.search_widening(params)
        assert [t.transaction_number for t in found] == ["T-1"]
        assert widened == ["the building anywhere in Dubai"]


class TestApi:
    def test_search_then_add_ticked_sales(self, job, dan):
        load(PULSE)
        res = client_for(dan).get(f"/api/jobs/{job.pk}/evidence/dld/")
        assert res.status_code == 200
        # Fewer than five exact matches, so the list is widened; T-1 is still in it.
        row = next(r for r in res.json()["results"] if r["transaction_number"] == "T-1")
        assert row["aed_per_sqft"] == "1765" and row["added"] is False
        add = client_for(dan).post(f"/api/jobs/{job.pk}/evidence/dld/", {"ids": [row["id"]]}, format="json")
        assert add.status_code == 201 and add.json()["added"] == 1
        comparable = JobComparable.objects.get(job=job).comparable
        assert (comparable.source, comparable.source_ref, comparable.status) == ("dld", "T-1", "sold")
        assert comparable.bua_sqft == Decimal("850") and comparable.created_by is None
        again = client_for(dan).get(f"/api/jobs/{job.pk}/evidence/dld/").json()["results"]
        assert next(r for r in again if r["transaction_number"] == "T-1")["added"] is True

    def test_a_sale_used_by_two_jobs_is_one_comparable(self, job, dan):
        load(PULSE)
        other = Job.objects.create(bank=job.bank, property=Property.objects.create(), valuer=dan)
        t = DldTransaction.objects.get(transaction_number="T-1")
        dld.add_to_job(job, [t.id])
        dld.add_to_job(other, [t.id])
        assert Comparable.objects.filter(source_ref="T-1").count() == 1

    def test_the_data_status_is_shown_and_nothing_can_be_uploaded(self, dan):
        load(PULSE)
        res = client_for(dan).get("/api/evidence/dld/")
        assert res.status_code == 200 and res.json()["count"] == 5
        assert client_for(dan).post("/api/evidence/dld/", {}, format="json").status_code == 405

    def test_adding_needs_a_valuer_on_the_job(self, job):
        load(PULSE)
        reviewer = User.objects.create(username="pat", email="pat@example.com")
        job.peer_reviewer = reviewer
        job.save()
        t = DldTransaction.objects.get(transaction_number="T-1")
        res = client_for(reviewer).post(f"/api/jobs/{job.pk}/evidence/dld/", {"ids": [t.id]}, format="json")
        assert res.status_code == 403
