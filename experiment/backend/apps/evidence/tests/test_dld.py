"""DLD sales as comparables, and reading a pasted listing."""
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.banks.models import Bank
from apps.evidence import dld, listing_parse
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


class TestApi:
    def test_search_then_add_ticked_sales(self, job, dan):
        load(PULSE)
        res = client_for(dan).get(f"/api/jobs/{job.pk}/evidence/dld/")
        assert res.status_code == 200
        row = res.json()["results"][0]
        assert row["transaction_number"] == "T-1" and row["aed_per_sqft"] == "1763.98" and row["added"] is False
        add = client_for(dan).post(f"/api/jobs/{job.pk}/evidence/dld/", {"ids": [row["id"]]}, format="json")
        assert add.status_code == 201 and add.json()["added"] == 1
        comparable = JobComparable.objects.get(job=job).comparable
        assert (comparable.source, comparable.source_ref, comparable.status) == ("dld", "T-1", "sold")
        assert comparable.bua_sqft == Decimal("850.35") and comparable.created_by is None
        assert client_for(dan).get(f"/api/jobs/{job.pk}/evidence/dld/").json()["results"][0]["added"] is True

    def test_a_sale_used_by_two_jobs_is_one_comparable(self, job, dan):
        load(PULSE)
        other = Job.objects.create(bank=job.bank, property=Property.objects.create(), valuer=dan)
        t = DldTransaction.objects.get(transaction_number="T-1")
        dld.add_to_job(job, [t.id])
        dld.add_to_job(other, [t.id])
        assert Comparable.objects.filter(source_ref="T-1").count() == 1

    def test_only_admins_upload_dld_data(self, dan):
        upload = SimpleUploadedFile("dld.csv", PULSE.encode(), content_type="text/csv")
        assert client_for(dan).post("/api/evidence/dld/", {"file": upload}, format="multipart").status_code == 403
        boss = User.objects.create(username="boss", email="boss@example.com", roles=[Role.ADMIN])
        upload = SimpleUploadedFile("dld.csv", PULSE.encode(), content_type="text/csv")
        res = client_for(boss).post("/api/evidence/dld/", {"file": upload}, format="multipart")
        assert res.status_code == 201 and res.json()["count"] == 5

    def test_adding_needs_a_valuer_on_the_job(self, job):
        load(PULSE)
        reviewer = User.objects.create(username="pat", email="pat@example.com")
        job.peer_reviewer = reviewer
        job.save()
        t = DldTransaction.objects.get(transaction_number="T-1")
        res = client_for(reviewer).post(f"/api/jobs/{job.pk}/evidence/dld/", {"ids": [t.id]}, format="json")
        assert res.status_code == 403


# A listing as it reads when copied from a portal page (made-up).
BAYUT_TEXT = """
Home > Dubai > Dubai Marina > Test Tower A
AED
1,450,000
1 Bed
2 Baths
850 sqft
Test Tower A, Test Project, Dubai Marina, Dubai
Spacious one bedroom with full marina views on a high floor.
Property Information
Type Apartment
Purpose For Sale
Floor no. 23
"""

PF_TEXT = """
2,100,000 AED
Property type Villa
Property size 2,400 sqft / 223 sqm
Bedrooms 3
Test Villas, Arabian Ranches, Dubai
"""


class TestPastedListing:
    def test_reads_a_bayut_listing(self):
        out = listing_parse.parse(BAYUT_TEXT, "https://www.bayut.com/property/details-1.html")
        assert out["source"] == "bayut" and out["status"] == "asking"
        read = (out["price_aed"], out["bua_sqft"], out["beds"], out["property_type"])
        assert read == ("1450000", "850", 1, "Apartment")
        assert (out["building_name"], out["community_name"]) == ("Test Tower A", "Dubai Marina")
        assert (out["floor"], out["view"]) == ("23", "Marina")
        everything = {"price_aed", "bua_sqft", "beds", "property_type", "building_name", "community_name"}
        assert set(out["found"]) == everything

    def test_reads_a_property_finder_listing(self):
        out = listing_parse.parse(PF_TEXT, "https://www.propertyfinder.ae/en/plp/buy/villa-1.html")
        assert out["source"] == "property_finder"
        assert (out["price_aed"], out["bua_sqft"], out["beds"], out["property_type"]) == ("2100000", "2400", 3, "Villa")

    def test_says_what_it_could_not_find(self):
        out = listing_parse.parse("Nice flat, call now", "")
        assert out["found"] == [] and out["source"] == "other"

    def test_the_endpoint_prefills_without_saving(self, job, dan):
        res = client_for(dan).post(
            f"/api/jobs/{job.pk}/evidence/parse/",
            {"text": BAYUT_TEXT, "link": "https://www.bayut.com/x"},
            format="json",
        )
        assert res.status_code == 200 and res.json()["price_aed"] == "1450000"
        assert not Comparable.objects.exists()
