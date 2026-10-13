"""Development settings.

SQLite database, console email backend, DEBUG on by default.
"""
from .base import *  # noqa: F401,F403
from .base import BASE_DIR, DEBUG, env_bool  # noqa: F401

DEBUG = env_bool("DEBUG", True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }
}

# Console email backend unless explicitly overridden.
import os  # noqa: E402

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)

ALLOWED_HOSTS = ["*"]

# Faster password hashing in development.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# Disable rate limiting in development/tests
RATELIMIT_ENABLE = False

# base.py decides to add the full-page cache middleware at import time, based
# on ITS DEBUG default (False) — before this module flips DEBUG to True.
# Local dev must never serve cached pages, so drop them here.
MIDDLEWARE = [
    m for m in MIDDLEWARE
    if "django.middleware.cache." not in m
]
