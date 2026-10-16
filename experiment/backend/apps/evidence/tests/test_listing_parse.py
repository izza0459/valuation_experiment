"""Reading a listing the valuer copied from a property portal."""
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.banks.models import Bank
from apps.evidence import listing_parse
from apps.evidence.models import Comparable
from apps.jobs.models import Job, Property

pytestmark = pytest.mark.django_db


@pytest.fixture
def dan():
    return User.objects.create(username="dan", email="dan@example.com", first_name="Dan")


@pytest.fixture
def job(dan):
    j = Job.objects.create(bank=Bank.objects.create(name="Bank"), property=Property.objects.create(), valuer=dan)
    j.summary.bua_sqft = Decimal("850")
    j.summary.save()
    return Job.objects.get(pk=j.pk)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


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
