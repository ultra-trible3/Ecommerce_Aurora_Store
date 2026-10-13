"""Banner management app configuration."""
from django.apps import AppConfig


class BannersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.banners"
    verbose_name = "Banners & Advertisements"

    def ready(self):
        import apps.banners.signals  # noqa: F401