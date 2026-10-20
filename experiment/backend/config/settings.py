"""
Django settings for the valuation platform.

Config-driven direction: job stages/transitions and tab field definitions
live as data (see apps.jobs.field_config and apps.jobs.workflow), not
hard-coded views, mirroring how Carforce defines flows via config.
"""
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env")

# Safe by default: a missing env var must never silently produce a
# debug-mode, known-secret, any-host deployment of a system holding client
# PII and title deeds.
DEBUG = env("DEBUG", default=False)

SECRET_KEY = env("DJANGO_SECRET_KEY", default=None)
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DEBUG is off. "
            "For local development, copy backend/.env.example to backend/.env."
        )
    SECRET_KEY = "dev-only-insecure-key-not-for-deployment"

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"] if DEBUG else []
)
# Render sets this to the service's own public address (…onrender.com).
if RENDER_HOST := env("RENDER_EXTERNAL_HOSTNAME", default=""):
    ALLOWED_HOSTS.append(RENDER_HOST)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.common",
    "apps.accounts",
    "apps.banks",
    "apps.presets",
    "apps.jobs",
    "apps.media_files",
    "apps.evidence",
    "apps.reports",
    "apps.register",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.audit.middleware.CurrentUserMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Default to sqlite for quick local dev without Docker; docker-compose and
# production set DATABASE_URL to Postgres (per CLAUDE.md: Postgres 16,
# AWS me-central-1).
DATABASES = {
    "default": env.db(
        "DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
    )
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
# Dubai operations; stored timestamps stay UTC per Django convention.
TIME_ZONE = "Asia/Dubai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # Job endpoints add object-level RBAC on top (see
    # apps.accounts.permissions); this is the authenticated floor.
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_THROTTLE_RATES": {"login": "10/min"},
}

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"]
)
CORS_ALLOW_CREDENTIALS = True
# Session auth + credentialed CORS means the frontend's unsafe methods will
# need a CSRF token; the frontend origin has to be trusted for that to work.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=CORS_ALLOWED_ORIGINS)

if DEBUG:
    # Sharing a dev laptop through an ngrok tunnel: the web app forwards
    # /api/... here, so requests carry the tunnel's address.
    NGROK_DOMAINS = ["ngrok-free.app", "ngrok-free.dev", "ngrok.app"]
    ALLOWED_HOSTS += [f".{d}" for d in NGROK_DOMAINS]
    CSRF_TRUSTED_ORIGINS += [f"https://*.{d}" for d in NGROK_DOMAINS]

X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

if not DEBUG:
    # Terminated at the load balancer in AWS me-central-1.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
# Without a worker (dev.sh, tests) background tasks run inline in the request.
# Production runs the docker-compose `celery` worker and sets this false.
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=DEBUG)
# An issue request older than this is treated as lost (e.g. the worker died)
# and may be requested again.
ISSUE_TASK_TIMEOUT_SECONDS = env.int("ISSUE_TASK_TIMEOUT_SECONDS", default=600)

# Outgoing email (the report sent to the bank). With no EMAIL_HOST_USER the
# message is printed to the server log instead of being sent. For Gmail use
# smtp.gmail.com:587 and an app password (not the account password).
EMAIL_HOST = env("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
# Give up on an unreachable mail server quickly, so the delivery log shows why
# instead of the request hanging until the proxy cuts it off.
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
    if EMAIL_HOST_USER
    else "django.core.mail.backends.console.EmailBackend"
)
# Or send through an email service's web API (HTTPS), for hosting that
# blocks SMTP such as Render's free plan: EMAIL_API_PROVIDER = brevo, resend
# or sendgrid, with that service's EMAIL_API_KEY. Takes precedence over SMTP.
EMAIL_API_PROVIDER = env("EMAIL_API_PROVIDER", default="").strip().lower()
EMAIL_API_PROVIDERS = {"brevo", "resend", "sendgrid"}
if EMAIL_API_PROVIDER:
    if EMAIL_API_PROVIDER not in EMAIL_API_PROVIDERS:
        raise ImproperlyConfigured(
            f"EMAIL_API_PROVIDER must be one of {', '.join(sorted(EMAIL_API_PROVIDERS))}."
        )
    EMAIL_BACKEND = f"anymail.backends.{EMAIL_API_PROVIDER}.EmailBackend"
    ANYMAIL = {f"{EMAIL_API_PROVIDER.upper()}_API_KEY": env("EMAIL_API_KEY", default="")}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default=EMAIL_HOST_USER or "valuations@localhost")
# Optional: always copy this address (e.g. the sender's own mailbox) on reports sent to a bank.
REPORT_EMAIL_BCC = env.list("REPORT_EMAIL_BCC", default=[])
# Demo / staging: every report goes to these addresses instead of the bank
# contact picked, marked with who it would have gone to. Unset in production.
REPORT_EMAIL_REDIRECT_TO = env.list("REPORT_EMAIL_REDIRECT_TO", default=[])

# S3 storage (UAE region per CLAUDE.md). Left unconfigured for local dev;
# uploads fall back to local filesystem until AWS credentials are supplied.
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="me-central-1")

# Business defaults — see CLAUDE.md §11 "Open questions". Mark TODO, not blocking.
FORCED_SALE_DISCOUNT_PCT_DEFAULT = env.float(
    "FORCED_SALE_DISCOUNT_PCT_DEFAULT", default=10.0
)  # TODO: confirm 10% vs 15%, possibly per-bank (Bank.rules).
AVM_DEVIATION_THRESHOLD_PCT = env.float("AVM_DEVIATION_THRESHOLD_PCT", default=10.0)
VALUATION_RETENTION_YEARS = 5  # DLD Administrative Resolution 67/2020.

SQFT_PER_SQM = 10.76391

# RICS: peer review is a second valuer checking the work (CLAUDE.md §2), so a
# job can't go to review with its own valuer as the reviewer. Turn off only if
# the firm accepts that, e.g. while one person holds every role.
PEER_REVIEW_REQUIRES_INDEPENDENT_REVIEWER = env.bool("PEER_REVIEW_REQUIRES_INDEPENDENT_REVIEWER", default=True)

# Printed on every report. Placeholders until the final branding arrives
# (CLAUDE.md §11).
REPORT_FIRM_NAME = env("REPORT_FIRM_NAME", default="Bayut Valuation Services")
# Demo: signing off doesn't wait for signatories' RERA licences on file or for
# approved wording in place of placeholder text. Missing required fields still
# block. Set DEMO_MODE=false before any report goes to a bank.
DEMO_MODE = env.bool("DEMO_MODE", default=True)
# The registered legal name the signatory confirms the report is authorised
# by. Left empty, the report shows a placeholder and cannot be issued.
# TODO: the firm name stands in until the registered legal name is confirmed
# (demo only); set REPORT_FIRM_LEGAL_NAME for real reports.
REPORT_FIRM_LEGAL_NAME = env("REPORT_FIRM_LEGAL_NAME", default=REPORT_FIRM_NAME)
REPORT_FIRM_ADDRESS = env(
    "REPORT_FIRM_ADDRESS", default="[Firm address – to be confirmed], Dubai, United Arab Emirates"
)

# Generated PDFs. Local disk in development; production swaps in S3 (UAE
# region) through STORAGES without touching the report code.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
