import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core utilities, shared mixins and middleware"

    def ready(self):
        # Logging is already configured at this point (django.setup() runs
        # dictConfig before the app registry is populated), so this line is
        # the single startup entry for every entry point.
        logger.info("Application startup complete")
