"""Signing in through Cloudflare Access: the email in Cloudflare's signed
token picks the user, and their roles come from the backend."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from rest_framework.test import APIClient

from apps.accounts import cloudflare_access
from apps.accounts.models import Role, User

pytestmark = pytest.mark.django_db

TEAM = "team.cloudflareaccess.com"
AUD = "test-aud-tag"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def access_on(settings, monkeypatch):
    settings.CF_ACCESS_TEAM_DOMAIN = TEAM
    settings.CF_ACCESS_AUD = AUD
    # Cloudflare's published keys, without the network.
    monkeypatch.setattr(cloudflare_access, "signing_key", lambda token: KEY.public_key())


def token(email="dan@dubizzlelabs.com", aud=AUD, iss=f"https://{TEAM}", key=KEY, expires_in=300):
    claims = {"aud": [aud], "iss": iss, "exp": int(time.time()) + expires_in}
    if email is not None:
        claims["email"] = email
    return jwt.encode(claims, key, algorithm="RS256")


def me(client=None, **kwargs):
    return (client or APIClient()).get("/api/auth/me/", HTTP_CF_ACCESS_JWT_ASSERTION=token(**kwargs)).json()


def person(email="dan@dubizzlelabs.com", **kwargs):
    return User.objects.create(username=email, email=email, **kwargs)


class TestCloudflareAccess:
    def test_signs_in_the_user_with_that_email_and_their_roles(self):
        person(roles=[Role.VALUER])
        body = me(email="Dan@DubizzleLabs.com")
        assert body["authenticated"] is True
        assert body["user"]["email"] == "dan@dubizzlelabs.com"
        assert body["user"]["roles"] == ["valuer"]
        assert body["cloudflare_sso"] is True

    def test_the_session_then_works_for_api_calls(self):
        person()
        client = APIClient()
        me(client)
        assert client.get("/api/jobs/").status_code == 200

    def test_a_shared_browser_switches_to_the_new_sso_person(self):
        person()
        person("sara@dubizzlelabs.com")
        client = APIClient()
        me(client)
        assert me(client, email="sara@dubizzlelabs.com")["user"]["email"] == "sara@dubizzlelabs.com"

    def test_someone_new_waits_for_an_admin(self):
        body = me(email="new@dubizzlelabs.com")
        assert body == {"authenticated": False, "sso_email": "new@dubizzlelabs.com", "code": "access_requested",
                        "detail": "An admin needs to approve your access. Try again once they have."}
        assert User.objects.get(email="new@dubizzlelabs.com").access_request == User.PENDING

    def test_a_deactivated_user_stays_out(self):
        person(is_active=False)
        assert me()["code"] == "no_access"

    @pytest.mark.parametrize("bad", [
        {"key": OTHER_KEY},
        {"aud": "another-app"},
        {"iss": "https://evil.cloudflareaccess.com"},
        {"expires_in": -60},
        {"email": None},
    ])
    def test_a_token_that_doesnt_check_out_signs_nobody_in(self, bad):
        person()
        assert me(**bad) == {"authenticated": False}

    def test_a_bare_email_header_is_not_trusted(self):
        person()
        res = APIClient().get("/api/auth/me/", HTTP_CF_ACCESS_AUTHENTICATED_USER_EMAIL="dan@dubizzlelabs.com")
        assert res.json() == {"authenticated": False}

    def test_the_password_form_is_off(self):
        person()
        res = APIClient().post("/api/auth/login/", {"email": "dan@dubizzlelabs.com", "password": "x"}, format="json")
        assert res.json()["code"] == "sso_only"
        assert APIClient().get("/api/auth/config/").json()["cloudflare_sso"] is True

    def test_off_when_not_configured(self, settings):
        settings.CF_ACCESS_AUD = ""
        person()
        assert me() == {"authenticated": False}
        assert APIClient().get("/api/auth/config/").json()["cloudflare_sso"] is False
