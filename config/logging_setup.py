"""Single place where the project's logging is configured.

Django installs the ``LOGGING`` dict returned by :func:`build_logging_config`
exactly once during ``django.setup()`` (for the dev server, gunicorn, every
management command and the test suite), so there is no risk of duplicated
handlers or recursive logging.

Layout produced inside ``<BASE_DIR>/logs``:

* ``server.log``   -- every level (DEBUG and above)
* ``debug.log``    -- DEBUG only
* ``info.log``     -- INFO only
* ``warning.log``  -- WARNING only
* ``error.log``    -- ERROR only
* ``critical.log`` -- CRITICAL only

Every file rotates at 10 MB and keeps five backups, encoded as UTF-8.  The
threshold that reaches the files is controlled by the ``LOG_LEVEL``
environment variable (default ``DEBUG``); the console always shows INFO and
above.

.. note::
   ``logging.handlers.RotatingFileHandler`` is not safe when several OS
   processes write to the *same* file, so this configuration assumes a single
   server worker.  If you run gunicorn with ``--workers > 1`` either ship the
   files with an external log collector / the process manager, or give every
   worker its own file (for example add a ``%(process)d`` suffix to the
   filenames below).
"""
from __future__ import annotations

import atexit
import logging
import os
import sys
from pathlib import Path

# Resolved locally (instead of importing Django settings) so this module can
# be imported while the settings module itself is still being evaluated.
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"

LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
LOG_BACKUP_COUNT = 5

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(module)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

_shutdown_registered = False


class ExactLevelFilter(logging.Filter):
    """Pass only the records whose level matches exactly.

    A plain handler ``level`` would also let higher severities through, so
    ``debug.log`` would otherwise receive INFO/ERROR lines as well.
    """

    def __init__(self, level):
        super().__init__()
        if isinstance(level, str):
            level = logging.getLevelName(level.strip().upper())
        self.level = int(level)

    def filter(self, record):  # noqa: A003 - matches logging.Filter's API
        return record.levelno == self.level


def resolve_level(value=None):
    """Return a valid level name, falling back to ``DEBUG``."""
    candidate = value if value is not None else os.environ.get("LOG_LEVEL", "")
    candidate = str(candidate).strip().upper()
    return candidate if candidate in _LEVELS else "DEBUG"


def ensure_log_dir():
    """Create the log directory. Returns ``True`` when it is usable."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as exc:
        print(
            f"[logging_setup] Could not create log directory {LOG_DIR}: {exc}. "
            "Falling back to console-only logging.",
            file=sys.stderr,
        )
        return False


def _console_handler():
    return {
        "class": "logging.StreamHandler",
        "formatter": "standard",
        "level": "INFO",
        "stream": "ext://sys.stderr",
    }


def _file_handler(filename, level, filters=None):
    handler = {
        "class": "logging.handlers.RotatingFileHandler",
        "formatter": "standard",
        "level": level,
        "filename": str(LOG_DIR / filename),
        "maxBytes": LOG_MAX_BYTES,
        "backupCount": LOG_BACKUP_COUNT,
        "encoding": "utf-8",
        "delay": True,
    }
    if filters:
        handler["filters"] = filters
    return handler


def _console_only_config():
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {"format": LOG_FORMAT, "datefmt": DATE_FORMAT},
        },
        "handlers": {"console": _console_handler()},
        "root": {"level": "INFO", "handlers": ["console"]},
    }


def build_logging_config(level=None):
    """Return the ``LOGGING`` dict consumed by Django's ``dictConfig``."""
    _register_shutdown_hook()
    level = resolve_level(level)

    if not ensure_log_dir():
        return _console_only_config()

    handlers = {
        "console": _console_handler(),
        "file_server": _file_handler("server.log", level),
        "file_debug": _file_handler("debug.log", "DEBUG", ["exact_debug"]),
        "file_info": _file_handler("info.log", "INFO", ["exact_info"]),
        "file_warning": _file_handler("warning.log", "WARNING", ["exact_warning"]),
        "file_error": _file_handler("error.log", "ERROR", ["exact_error"]),
        "file_critical": _file_handler("critical.log", "CRITICAL", ["exact_critical"]),
    }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {"format": LOG_FORMAT, "datefmt": DATE_FORMAT},
        },
        "filters": {
            "exact_debug": {
                "()": "config.logging_setup.ExactLevelFilter",
                "level": "DEBUG",
            },
            "exact_info": {
                "()": "config.logging_setup.ExactLevelFilter",
                "level": "INFO",
            },
            "exact_warning": {
                "()": "config.logging_setup.ExactLevelFilter",
                "level": "WARNING",
            },
            "exact_error": {
                "()": "config.logging_setup.ExactLevelFilter",
                "level": "ERROR",
            },
            "exact_critical": {
                "()": "config.logging_setup.ExactLevelFilter",
                "level": "CRITICAL",
            },
        },
        "handlers": handlers,
        "root": {
            "level": level,
            "handlers": [
                "console",
                "file_server",
                "file_debug",
                "file_info",
                "file_warning",
                "file_error",
                "file_critical",
            ],
        },
        "loggers": {
            # App loggers propagate to the root handlers above, so every record
            # is written exactly once per file (no duplicate handlers).
            "apps": {"handlers": [], "level": level, "propagate": True},
            # Django's built-in request/security loggers already attach the full
            # traceback for HTTP errors, so keep them but never duplicate them.
            "django.request": {"handlers": [], "level": "WARNING", "propagate": True},
            "django.security": {"handlers": [], "level": "WARNING", "propagate": True},
            "django.server": {"handlers": [], "level": "INFO", "propagate": True},
            # Very chatty during development; keep the debug log readable.
            "django.utils.autoreload": {
                "handlers": [],
                "level": "WARNING",
                "propagate": True,
            },
            # Third-party libraries that are very verbose at DEBUG.
            "PIL": {"handlers": [], "level": "INFO", "propagate": True},
            "urllib3.connectionpool": {
                "handlers": [],
                "level": "INFO",
                "propagate": True,
            },
        },
    }


def _log_shutdown():
    try:
        logging.getLogger("config").info("Server shutting down")
        for handler in logging.getLogger().handlers:
            handler.flush()
    except Exception:  # pragma: no cover - never raise while shutting down
        pass


def _register_shutdown_hook():
    global _shutdown_registered
    if not _shutdown_registered:
        atexit.register(_log_shutdown)
        _shutdown_registered = True
