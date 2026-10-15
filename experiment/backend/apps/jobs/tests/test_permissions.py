"""RBAC: a signed-in user sees only jobs they hold a role on
(CLAUDE.md §3 roles, §7 RBAC)."""
import pytest

from apps.accounts.models import Role, User
from apps.accounts.permissions import can_access_job, roles_on_job, visible_jobs
from apps.banks.models import Bank
from apps.jobs.models import Job, Property

pytestmark = pytest.mark.django_db


@pytest.fixture
def bank():
    return Bank.objects.create(name="Test Bank")


@pytest.fixture
def property_obj():
    return Property.objects.create(building_name="Marina Gate 1")


def make_user(email, roles=None, **kwargs):
    return User.objects.create(
        username=email.split("@")[0], email=email, roles=roles or [], **kwargs
    )


class TestRolesOnJob:
    def test_detects_every_role_a_user_holds(self, bank, property_obj):
        dan = make_user("dan@example.com")
        job = Job.objects.create(
            bank=bank, property=property_obj, valuer=dan, inspected_by=dan
        )
        assert roles_on_job(dan, job) == {Role.VALUER, Role.INSPECTOR}

    def test_signing_valuer_counts_as_a_valuer(self, bank, property_obj):
        signer = make_user("signer@example.com")
        job = Job.objects.create(bank=bank, property=property_obj, registered_valuer=signer)
        assert Role.VALUER in roles_on_job(signer, job)

    def test_unrelated_user_holds_nothing(self, bank, property_obj):
        job = Job.objects.create(bank=bank, property=property_obj)
        assert roles_on_job(make_user("nobody@example.com"), job) == set()


class TestJobVisibility:
    def test_user_sees_only_their_own_jobs(self, bank, property_obj):
        dan = make_user("dan@example.com")
        someone_else = make_user("other@example.com")
        mine = Job.objects.create(bank=bank, property=property_obj, valuer=dan)
        theirs = Job.objects.create(bank=bank, property=property_obj, valuer=someone_else)

        visible = visible_jobs(Job.objects.all(), dan)

        assert mine in visible
        assert theirs not in visible

    def test_platform_admin_sees_everything(self, bank, property_obj):
        admin = make_user("admin@example.com", roles=[Role.ADMIN])
        job = Job.objects.create(bank=bank, property=property_obj)
        assert job in visible_jobs(Job.objects.all(), admin)

    def test_django_staff_sees_everything(self, bank, property_obj):
        staff = make_user("staff@example.com", is_staff=True)
        job = Job.objects.create(bank=bank, property=property_obj)
        assert job in visible_jobs(Job.objects.all(), staff)

    def test_a_job_is_listed_once_even_with_several_roles(self, bank, property_obj):
        dan = make_user("dan@example.com")
        Job.objects.create(
            bank=bank, property=property_obj, valuer=dan, inspected_by=dan, peer_reviewer=dan
        )
        assert visible_jobs(Job.objects.all(), dan).count() == 1

    def test_peer_reviewer_can_access_the_job_they_review(self, bank, property_obj):
        reviewer = make_user("peer@example.com")
        job = Job.objects.create(bank=bank, property=property_obj, peer_reviewer=reviewer)
        assert can_access_job(reviewer, job) is True
