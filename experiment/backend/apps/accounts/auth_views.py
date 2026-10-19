"""Sign-in for the web app (session cookie).

Email + password is the interim method: Google Workspace SSO (CLAUDE.md §8)
replaces it, and `me()` is the contract the frontend keeps using either way.
"""

from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .permissions import can_create_jobs, is_platform_admin


def describe_user(user) -> dict:
    return {
        "id": user.pk,
        "name": str(user),
        "email": user.email,
        "roles": list(user.roles or []),
        "is_admin": is_platform_admin(user),
        "can_create_jobs": can_create_jobs(user),
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
