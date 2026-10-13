"""Base settings shared by all environments.

All secrets and environment-specific values are read from environment
variables (optionally loaded from a ``.env`` file).  Nothing secret is ever
hard-coded in the repository.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

from django.utils.translation import gettext_lazy

from config.logging_setup import build_logging_config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env file if present (no-op when it does not exist).
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    """Read a boolean environment variable."""
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    """Read an integer environment variable."""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "insecure-dev-key-change-me-in-production",
)

DEBUG = env_bool("DEBUG", False)

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

# --------------------------------------------------------------------------
# Application definition
# --------------------------------------------------------------------------
DJANGO_APPS = [
    "modeltranslation",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.sitemaps",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.inventory",
    "apps.cart",
    "apps.coupons",
    "apps.orders",
    "apps.payments",
    "apps.reviews",
    "apps.notifications",
    "apps.dashboard",
    "apps.banners",
]

INSTALLED_APPS = DJANGO_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.RequestLoggingMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.SingleDeviceSessionMiddleware",
    "apps.core.middleware.RateLimitMiddleware",
    "apps.core.middleware.SecurityHeadersMiddleware",
    "apps.core.middleware.CartSessionMiddleware",
]

# Cache middleware (add in production)
if not DEBUG:
    MIDDLEWARE.insert(1, "django.middleware.cache.UpdateCacheMiddleware")
    MIDDLEWARE.append("django.middleware.cache.FetchFromCacheMiddleware")

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
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site_context",
                "apps.core.context_processors.notifications_context",
                "apps.core.context_processors.js_catalog",
                "apps.cart.context_processors.cart_context",
                "apps.dashboard.context_processors.portal_context",
                "apps.banners.context_processors.active_banners",
                "apps.catalog.context_processors.recently_viewed_products",
                "apps.catalog.context_processors.logo_marquee",
                "apps.catalog.context_processors.deals_mosaic",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --------------------------------------------------------------------------
# Password validation
# --------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Custom user model
# --------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "core:home"

# --------------------------------------------------------------------------
# Internationalization
# --------------------------------------------------------------------------
LANGUAGE_CODE = "en"

TIME_ZONE = os.environ.get("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("en", "English"),
    ("ar", "العربية"),
]

LOCALE_PATHS = [
    BASE_DIR / "locale",
]

LANGUAGE_COOKIE_NAME = "django_language"
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365  # 1 year
LANGUAGE_COOKIE_HTTPONLY = True
LANGUAGE_COOKIE_SECURE = not DEBUG
LANGUAGE_COOKIE_SAMESITE = "Lax"

# --------------------------------------------------------------------------
# Modeltranslation
# --------------------------------------------------------------------------
MODELTRANSLATION_DEFAULT_LANGUAGE = "en"
MODELTRANSLATION_LANGUAGES = ("en", "ar")
# English pages must never fall back to Arabic; Arabic falls back to English.
MODELTRANSLATION_FALLBACK_LANGUAGES = {
    "default": ("en",),
    "ar": ("en",),
}
MODELTRANSLATION_PREPOPULATE_LANGUAGE = "en"

# --------------------------------------------------------------------------
# Static & media files
# --------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Database (overridden per environment)
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# --------------------------------------------------------------------------
# Authentication backends / email
# --------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "shop@example.com"
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# --------------------------------------------------------------------------
# Messages (toast notifications)
# --------------------------------------------------------------------------
from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {
    message_constants.DEBUG: "secondary",
    message_constants.INFO: "info",
    message_constants.SUCCESS: "success",
    message_constants.WARNING: "warning",
    message_constants.ERROR: "danger",
}

# --------------------------------------------------------------------------
# Cache (used by rate limiter + performance caching)
# --------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ecommerce-cache",
    }
}

# Use Redis if available (production)
if os.environ.get("REDIS_URL"):
    CACHES["default"] = {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": os.environ.get("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "COMPRESSOR": "django_redis.compressors.zlib.ZlibCompressor",
            "IGNORE_EXCEPTIONS": True,
        },
        "KEY_PREFIX": "ecommerce",
    }

# Cache middleware settings
CACHE_MIDDLEWARE_ALIAS = "default"
CACHE_MIDDLEWARE_SECONDS = 60 * 15  # 15 minutes
CACHE_MIDDLEWARE_KEY_PREFIX = "ecommerce"

# --------------------------------------------------------------------------
# Sessions / security (production overrides in production.py)
# --------------------------------------------------------------------------
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 60 * 60 * 24 * 14)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

# --------------------------------------------------------------------------
# Site / commerce settings (editable in /management/settings/)
# --------------------------------------------------------------------------
SITE_NAME = os.environ.get("SITE_NAME", "Aurora Store")
# gettext_lazy so the default participates in the PO catalog and the context
# processor can localize it per-request (see apps/core/context_processors.py).
SITE_TAGLINE = os.environ.get(
    "SITE_TAGLINE", gettext_lazy("Modern essentials, delivered fast.")
)
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "support@example.com")
SUPPORT_PHONE = os.environ.get("SUPPORT_PHONE", "+1 (555) 010-2030")
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000").rstrip("/")
CURRENCY = os.environ.get("CURRENCY", "USD")
CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "$")
TAX_RATE = float(os.environ.get("TAX_RATE", "0.0"))
DEFAULT_PAGINATION = env_int("DEFAULT_PAGINATION", 12)

# Order cancellation window (minutes after order placement)
# 0 = no time limit (cancel anytime in CANCELLABLE_STATUSES)
CANCELLATION_WINDOW_MINUTES = env_int("CANCELLATION_WINDOW_MINUTES", 30)

# --------------------------------------------------------------------------
# Payments (secret keys come from the environment only)
# --------------------------------------------------------------------------
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLIC_KEY = os.environ.get("STRIPE_PUBLIC_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID", "")
PAYPAL_SECRET = os.environ.get("PAYPAL_SECRET", "")
PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox")

# --------------------------------------------------------------------------
# File upload validation
# --------------------------------------------------------------------------
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 5 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int(
    "FILE_UPLOAD_MAX_MEMORY_SIZE", 5 * 1024 * 1024
)
ALLOWED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp", ".gif"]
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB

# --------------------------------------------------------------------------
# Rate limiting (simple cache-based throttle)
# --------------------------------------------------------------------------
RATELIMIT_ENABLE = env_bool("RATELIMIT_ENABLE", True)

# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Rate limiting (simple cache-based throttle)
# --------------------------------------------------------------------------
RATELIMIT_ENABLE = env_bool("RATELIMIT_ENABLE", True)
RATELIMIT_REQUESTS_PER_MINUTE = env_int("RATELIMIT_REQUESTS_PER_MINUTE", 120)
RATELIMIT_REQUESTS_PER_HOUR = env_int("RATELIMIT_REQUESTS_PER_HOUR", 2000)

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
# All logging behaviour lives in config/logging_setup.py (stdio console at
# INFO+ plus per-severity rotating files under logs/). Django applies this
# dict exactly once during django.setup(), for every entry point.
LOGGING = build_logging_config()
