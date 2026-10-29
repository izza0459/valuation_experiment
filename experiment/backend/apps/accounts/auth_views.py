"""Sign-in for the web app (session cookie).

Email + password is the interim method: Google Workspace SSO (CLAUDE.md §8)
replaces it, and `me()` is the contract the frontend keeps using either way.
"""

import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import User
from .permissions import can_create_jobs, is_platform_admin

logger = logging.getLogger(__name__)


def describe_user(user) -> dict:
    return {
        "id": user.pk,
        "name": str(user),
        "email": user.email,
        "roles": list(user.roles or []),
        "is_admin": is_platform_admin(user),
        "can_create_jobs": can_create_jobs(user),
        # A manager sees their team on the dashboard.
        "is_manager": user.direct_reports.filter(is_active=True).exists(),
    }


class LoginThrottle(AnonRateThrottle):
    """Slows password guessing. Per client address, since the account being
    guessed at is exactly what an attacker varies."""

    scope = "login"


class MeView(APIView):
    """Who is signed in. Answers 200 either way so the app can tell
    'not signed in' apart from an actual failure."""

    permission_classes = [AllowAny]
    # Session auth must be listed: with no authenticators DRF replaces the
    # session user Django resolved with AnonymousUser. (A GET is never subject
    # to its CSRF check.)
    authentication_classes = [SessionAuthentication]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"authenticated": False})
        return Response({"authenticated": True, "user": describe_user(request.user)})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    """CSRF-protected even though nobody is signed in yet: otherwise a hostile
    page could sign a victim into the attacker's account."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginThrottle]

    def post(self, request):
        email = request.data.get("email") if isinstance(request.data, dict) else None
        password = request.data.get("password") if isinstance(request.data, dict) else None
        if not isinstance(email, str) or not isinstance(password, str) or not email or not password:
            return Response({"code": "validation", "detail": "Enter your email and password."}, status=400)

        # As typed first, then lower-cased: addresses created by hand in the
        # Django admin may not have been normalised.
        user = authenticate(request, username=email.strip(), password=password) or authenticate(
            request, username=email.strip().lower(), password=password
        )
        if user is None or not user.is_active:
            # One message for every failure: it must not reveal which emails exist.
            return Response({"code": "invalid_credentials", "detail": "Invalid email or password."}, status=400)

        login(request, user)
        return Response({"authenticated": True, "user": describe_user(user)})


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        logout(request)
        return Response(status=204)


class AuthConfigView(APIView):
    """What the sign-in screen offers: the Google button when it's set up."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"google_client_id": settings.GOOGLE_OAUTH_CLIENT_ID})


def verify_google_token(credential: str) -> dict | None:
    """Google checks the ID token's signature and expiry for us; we check it
    was issued to our client. None if it isn't valid."""
    url = "https://oauth2.googleapis.com/tokeninfo?" + urllib.parse.urlencode({"id_token": credential})
    try:
        with urllib.request.urlopen(url, timeout=10) as res:
            info = json.load(res)
    except Exception:
        logger.warning("Google token check failed")
        return None
    if info.get("aud") != settings.GOOGLE_OAUTH_CLIENT_ID:
        return None
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        return None
    return info


@method_decorator(csrf_protect, name="dispatch")
class GoogleLoginView(APIView):
    """POST {"credential": <Google ID token>}. Signs in a user an admin has
    added. Anyone else from an allowed domain is recorded as waiting for
    access, for an admin to approve (with roles) or decline."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginThrottle]

    def post(self, request):
        if not settings.GOOGLE_OAUTH_CLIENT_ID:
            return Response({"code": "not_configured", "detail": "Google sign-in isn't set up."}, status=400)
        credential = request.data.get("credential") if isinstance(request.data, dict) else None
        info = verify_google_token(credential) if isinstance(credential, str) and credential else None
        if info is None or str(info.get("email_verified")).lower() != "true" or not info.get("email"):
            return Response({"code": "invalid_credentials", "detail": "Google sign-in failed. Try again."},
                            status=400)
        email = info["email"].strip().lower()
        domain = email.rsplit("@", 1)[-1]
        if settings.GOOGLE_ALLOWED_DOMAINS and domain not in settings.GOOGLE_ALLOWED_DOMAINS:
            return Response({"code": "wrong_domain", "detail": "Sign in with your company Google account."},
                            status=403)

        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            user = User(username=email, email=email, first_name=info.get("given_name", "")[:150],
                        last_name=info.get("family_name", "")[:150], is_active=False,
                        access_request=User.PENDING, access_requested_at=timezone.now())
            user.set_unusable_password()
            user.save()
        if not user.is_active:
            if user.access_request == User.DECLINED:
                return Response({"code": "no_access", "detail": "You don't have access. Ask an admin."},
                                status=403)
            if not user.access_request:
                # Deactivated by an admin: not a new request.
                return Response({"code": "no_access", "detail": "Your account is deactivated. Ask an admin."},
                                status=403)
            return Response({"code": "access_requested",
                             "detail": "An admin needs to approve your access. Try again once they have."},
                            status=403)
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response({"authenticated": True, "user": describe_user(user)})
