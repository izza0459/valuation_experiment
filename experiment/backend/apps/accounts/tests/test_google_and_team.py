"""Google sign-in, access requests and the reporting line."""
from unittest import mock

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.jobs.tests.test_tabs import client_for, make_user

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def google(settings):
    cache.clear()  # the sign-in throttle counts in the cache
    settings.GOOGLE_OAUTH_CLIENT_ID = "client-1"
    settings.GOOGLE_ALLOWED_DOMAINS = ["dubizzlelabs.com"]


def sign_in(email, verified="true"):
    info = {"aud": "client-1", "iss": "https://accounts.google.com", "email": email, "email_verified": verified,
            "given_name": "New", "family_name": "Person"}
    with mock.patch("apps.accounts.auth_views.verify_google_token", return_value=info):
        return APIClient().post("/api/auth/google/", {"credential": "x"}, format="json")


def person(name, email, **kwargs):
    user = make_user(name, **kwargs)
    User.objects.filter(pk=user.pk).update(email=email)
    return user


class TestGoogleSignIn:
    def test_an_added_user_signs_in(self):
        person("dan", "dan@dubizzlelabs.com")
        res = sign_in("Dan@dubizzlelabs.com")
        assert res.status_code == 200 and res.json()["user"]["email"] == "dan@dubizzlelabs.com"

    def test_someone_new_waits_for_an_admin(self):
        res = sign_in("new@dubizzlelabs.com")
        assert res.status_code == 403 and res.json()["code"] == "access_requested"
        user = User.objects.get(email="new@dubizzlelabs.com")
        assert not user.is_active and user.access_request == User.PENDING and not user.has_usable_password()
        assert sign_in("new@dubizzlelabs.com").json()["code"] == "access_requested"
        assert User.objects.filter(email="new@dubizzlelabs.com").count() == 1

    def test_the_admin_approves_them_and_they_get_in(self):
        sign_in("new@dubizzlelabs.com")
        api = client_for(make_user("root", roles=[Role.ADMIN]))
        waiting = api.get("/api/admin/users/", {"waiting": 1}).json()
        assert [u["email"] for u in waiting] == ["new@dubizzlelabs.com"]
        user = User.objects.get(email="new@dubizzlelabs.com")
        res = api.patch(f"/api/admin/users/{user.pk}/", {"is_active": True, "roles": ["valuer"]}, format="json")
        assert res.status_code == 200 and res.json()["access_request"] == ""
        assert sign_in("new@dubizzlelabs.com").status_code == 200

    def test_declined_or_deactivated_people_stay_out(self):
        sign_in("new@dubizzlelabs.com")
        User.objects.filter(email="new@dubizzlelabs.com").update(access_request=User.DECLINED)
        assert sign_in("new@dubizzlelabs.com").json()["code"] == "no_access"
        person("gone", "gone@dubizzlelabs.com", is_active=False)
        assert sign_in("gone@dubizzlelabs.com").json()["code"] == "no_access"

    def test_other_domains_and_unverified_emails_are_refused(self):
        assert sign_in("x@gmail.com").json()["code"] == "wrong_domain"
        assert sign_in("x@dubizzlelabs.com", verified="false").status_code == 400
        assert not User.objects.filter(email__startswith="x@").exists()

    def test_the_sign_in_screen_learns_the_client_id(self):
        assert APIClient().get("/api/auth/config/").json() == {"google_client_id": "client-1"}


class TestReportingLine:
    def test_a_manager_is_set_and_loops_are_refused(self):
        api = client_for(make_user("root", roles=[Role.ADMIN]))
        boss, amy = make_user("boss"), make_user("amy")
        assert api.patch(f"/api/admin/users/{amy.pk}/", {"manager": boss.pk}, format="json").status_code == 200
        res = api.patch(f"/api/admin/users/{boss.pk}/", {"manager": amy.pk}, format="json")
        assert res.status_code == 400 and "manager" in res.json()
        users = {u["email"]: u for u in api.get("/api/admin/users/").json()}
        assert users["boss@example.com"]["team_size"] == 1
        assert users["amy@example.com"]["manager_name"] == "Boss"
        assert client_for(boss).get("/api/auth/me/").json()["user"]["is_manager"] is True
