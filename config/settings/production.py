"""Production settings.

Requires environment variables; set ``DATABASE_URL`` to use PostgreSQL.
"""
import os
from urllib.parse import urlparse

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env_bool  # noqa: F401

DEBUG = env_bool("DEBUG", False)

# --------------------------------------------------------------------------
# Database: PostgreSQL when DATABASE_URL is provided, SQLite otherwise.
# --------------------------------------------------------------------------
_db_url = os.environ.get("DATABASE_URL", "").strip()

if _db_url and not _db_url.startswith("sqlite"):
    parsed = urlparse(_db_url)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "localhost",
            "PORT": str(parsed.port or 5432),
            "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60),  # noqa: F405
            "OPTIONS": {"sslmode": os.environ.get("DB_SSLMODE", "prefer")},
        }
    }
elif _db_url.startswith("sqlite"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / _db_url.split("///")[-1],
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------
SECURE_BROWSER_XSS_FILTER = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

if env_bool("ENABLE_SSL", False):
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 60 * 60 * 24 * 30)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# --------------------------------------------------------------------------
# Static files served through WhiteNoise with compression + manifest
# --------------------------------------------------------------------------
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
