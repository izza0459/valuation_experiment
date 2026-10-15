import contextlib
from contextvars import ContextVar

# A ContextVar rather than threading.local: under ASGI several requests
# share one thread, so thread-local storage would attribute one user's
# edits to whichever request touched it last.
_current_user: ContextVar = ContextVar("audit_current_user", default=None)


def get_current_user():
    return _current_user.get()


@contextlib.contextmanager
def acting_as(user):
    """Attributes audit entries written inside the block to `user`, however
    the request was authenticated (the middleware below only sees the
    session user, not e.g. a token-authenticated DRF user)."""
    token = _current_user.set(user)
    try:
        yield
    finally:
        _current_user.reset(token)


class CurrentUserMiddleware:
    """Stashes the requesting user so model-level signal handlers (see
    apps.audit.signals) can attribute field changes without threading
    `user` through every call site."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with acting_as(getattr(request, "user", None)):
            return self.get_response(request)
