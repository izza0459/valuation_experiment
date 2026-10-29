"""Signing in and out (session cookie), and who the app thinks you are."""
import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-9"


@pytest.fixture(autouse=True)
def fresh_throttle():
    """The login throttle counts in the cache; keep tests from sharing it."""
    cache.clear()


def make_user(email="dan@example.com", roles=None, **kwargs):
    user = User.objects.create(username=email, email=email, roles=roles or [], first_name="Dan", **kwargs)
    user.set_password(PASSWORD)
    user.save()
    return user


def csrf_client():
    """A browser-like client that enforces CSRF, as the real app is."""
    client = APIClient(enforce_csrf_checks=True)
    client.get("/api/csrf/")
    return client, client.cookies["csrftoken"].value


def current_token(client):
    """Logging in rotates the CSRF token; a browser re-reads its cookie."""
    return client.cookies["csrftoken"].value


def login(client, token, email="dan@example.com", password=PASSWORD):
    return client.post("/api/auth/login/", {"email": email, "password": password}, format="json",
                       HTTP_X_CSRFTOKEN=token)


class TestLogin:
    def test_signs_in_and_returns_who_you_are(self):
        make_user(roles=[Role.VALUER])
        client, token = csrf_client()
        res = login(client, token)
        assert res.status_code == 200
        assert res.json()["user"] == {"id": 1, "name": "Dan", "email": "dan@example.com",
                                      "roles": ["valuer"], "is_admin": False,
                                      "can_create_jobs": True, "is_manager": False}

    def test_the_session_then_authenticates_api_calls(self):
        make_user()
        client, token = csrf_client()
        login(client, token)
        assert client.get("/api/jobs/").status_code == 200

    def test_an_unauthenticated_call_is_refused(self):
        assert APIClient().get("/api/jobs/").status_code in (401, 403)

    @pytest.mark.parametrize("email,password", [
        ("dan@example.com", "wrong-password-1"),
        ("nobody@example.com", PASSWORD),
    ])
    def test_a_wrong_email_or_password_gets_the_same_answer(self, email, password):
        """It must not reveal which addresses have accounts."""
        make_user()
        client, token = csrf_client()
        res = login(client, token, email, password)
        assert res.status_code == 400 and res.json()["code"] == "invalid_credentials"
        assert res.json()["detail"] == "Invalid email or password."

    def test_a_deactivated_user_cannot_sign_in(self):
        make_user(is_active=False)
        client, token = csrf_client()
        res = login(client, token)
        assert res.status_code == 400 and res.json()["detail"] == "Invalid email or password."

    def test_login_requires_the_csrf_token(self):
        """Otherwise a hostile page could sign a victim into the attacker's account."""
        make_user()
        client = APIClient(enforce_csrf_checks=True)
        res = client.post("/api/auth/login/", {"email": "dan@example.com", "password": PASSWORD}, format="json")
        assert res.status_code == 403

    @pytest.mark.parametrize("body", [{}, {"email": "x@example.com"}, {"password": "x"}, {"email": 1, "password": 2}])
    def test_missing_or_malformed_credentials(self, body):
        client, token = csrf_client()
        res = client.post("/api/auth/login/", body, format="json", HTTP_X_CSRFTOKEN=token)
        assert res.status_code == 400

    def test_an_address_typed_in_capitals_still_signs_in(self):
        make_user("dan@example.com")
        client, token = csrf_client()
        assert login(client, token, "Dan@Example.com").status_code == 200

    def test_guessing_is_throttled(self):
        make_user()
        client, token = csrf_client()
        codes = [login(client, token, password="nope-1234").status_code for _ in range(12)]
        assert 429 in codes


class TestMeAndLogout:
    def test_me_says_when_nobody_is_signed_in(self):
        res = APIClient().get("/api/auth/me/")
        assert res.status_code == 200 and res.json() == {"authenticated": False}

    def test_me_describes_the_signed_in_user_and_flags_admins(self):
        make_user(roles=[Role.ADMIN])
        client, token = csrf_client()
        login(client, token)
        me = client.get("/api/auth/me/").json()
        assert me["authenticated"] and me["user"]["is_admin"] is True

    def test_staff_count_as_admins(self):
        make_user(is_staff=True)
        client, token = csrf_client()
        login(client, token)
        assert client.get("/api/auth/me/").json()["user"]["is_admin"] is True

    def test_logout_ends_the_session(self):
        make_user()
        client, token = csrf_client()
        login(client, token)
        assert client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=current_token(client)).status_code == 204
        assert client.get("/api/auth/me/").json() == {"authenticated": False}
        assert client.get("/api/jobs/").status_code in (401, 403)

    def test_logout_requires_the_csrf_token(self):
        make_user()
        client, token = csrf_client()
        login(client, token)
        assert client.post("/api/auth/logout/").status_code == 403
