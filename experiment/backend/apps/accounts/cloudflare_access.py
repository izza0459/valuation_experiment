"""Sign-in through Cloudflare Access (the company SSO in front of the app).

Cloudflare signs in the visitor before a request reaches us and attaches a
signed JWT (Cf-Access-Jwt-Assertion) naming their email. We check that token
ourselves rather than trust a bare header, then sign in the user with that
email; their roles are whatever the backend holds for them.

Off unless CF_ACCESS_TEAM_DOMAIN and CF_ACCESS_AUD are set.
"""

import logging
from functools import lru_cache

import jwt
from django.conf import settings
from django.contrib.auth import login, logout

from .models import User

logger = logging.getLogger(__name__)

HEADER = "Cf-Access-Jwt-Assertion"


def enabled() -> bool:
    return bool(settings.CF_ACCESS_TEAM_DOMAIN and settings.CF_ACCESS_AUD)


@lru_cache(maxsize=1)
def _jwks() -> jwt.PyJWKClient:
    # Cloudflare rotates these keys; the client caches them and refetches
    # when a token names a key it hasn't seen.
    return jwt.PyJWKClient(f"https://{settings.CF_ACCESS_TEAM_DOMAIN}/cdn-cgi/access/certs", cache_keys=True)


def signing_key(token: str):
    return _jwks().get_signing_key_from_jwt(token).key


def verified_email(request) -> str | None:
    """The email Cloudflare Access vouches for on this request, lower-cased.
    None when SSO is off, there's no token, or the token doesn't check out."""
    if not enabled():
        return None
    token = request.headers.get(HEADER)
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            signing_key(token),
            algorithms=["RS256"],
            audience=settings.CF_ACCESS_AUD,
            issuer=f"https://{settings.CF_ACCESS_TEAM_DOMAIN}",
        )
    except jwt.PyJWTError as exc:
        logger.warning("Cloudflare Access token rejected: %s", exc)
        return None
    email = claims.get("email")
    # Service tokens carry no email: they never become a user.
    return email.strip().lower() if isinstance(email, str) and email.strip() else None


class CloudflareAccessMiddleware:
    """Keeps the Django session in step with who Cloudflare says is visiting:
    signs in the matching active user, and never lets a session that belongs
    to someone else (a shared browser) carry on under a new SSO identity."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        email = verified_email(request)
        if email:
            current = request.user
            if not (current.is_authenticated and current.email.lower() == email):
                if current.is_authenticated:
                    logout(request)
                user = User.objects.filter(email__iexact=email, is_active=True).first()
                if user is not None:
                    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)
