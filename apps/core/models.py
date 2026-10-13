"""Shared abstract models and model helpers."""
import unicodedata

from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


def generate_slug(instance, value, slug_field="slug", queryset=None, max_length=250):
    """Generate a unique slug for ``instance`` based on ``value``."""
    base_slug = slugify(value)[:max_length] or "item"
    slug = base_slug
    qs = queryset or instance.__class__._default_manager
    qs = qs.exclude(pk=instance.pk) if instance.pk else qs
    counter = 2
    while qs.filter(**{slug_field: slug}).exists():
        suffix = f"-{counter}"
        slug = base_slug[: max_length - len(suffix)] + suffix
        counter += 1
    return slug


def sync_default_language(instance, *field_names):
    """Mirror the English copy of ``field_names`` into the legacy base column.

    ``modeltranslation`` writes only the language specific column, but the base
    column is what raw SQL, exports and unique constraints (``Brand.name``)
    still rely on, so it is kept equal to the default language.
    """
    from django.conf import settings
    from django.utils.translation import override

    default_language = getattr(settings, "MODELTRANSLATION_DEFAULT_LANGUAGE", None)
    if not default_language:
        return instance
    with override(default_language):
        for field_name in field_names:
            # English copy if it exists, otherwise whatever the base column
            # holds (it is written directly by ``instance.name = ...``).
            value = getattr(instance, f"{field_name}_en", None) or instance.__dict__.get(
                field_name
            )
            if value:
                # Writing while the default language is active updates both
                # the base column and the ``_en`` column.
                setattr(instance, field_name, value)
    return instance


class TimeStampedModel(models.Model):
    """Abstract base model adding created/updated timestamps."""

    created_at = models.DateTimeField(_("Created"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("Updated"), auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-created_at",)


class SEOModel(models.Model):
    """Abstract SEO metadata fields."""

    meta_title = models.CharField(
        max_length=200, blank=True,
        help_text=_("Leave blank to use the object name."),
    )
    meta_description = models.CharField(
        max_length=300, blank=True,
        help_text=_("Recommended: 150-160 characters."),
    )
    meta_keywords = models.CharField(
        max_length=250, blank=True, help_text=_("Comma-separated keywords.")
    )
    canonical_slug = models.SlugField(
        max_length=250, blank=True,
        help_text=_("Optional canonical override."),
    )

    class Meta:
        abstract = True

    @property
    def seo_title(self):
        return self.meta_title or getattr(self, "name", str(self))

    @property
    def seo_description(self):
        if self.meta_description:
            return self.meta_description
        return (getattr(self, "description", "") or "")[:160]


class SlugModel(models.Model):
    """Abstract base model with a unique slug."""

    slug = models.SlugField(max_length=250, unique=True, db_index=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        sync_default_language(self, "name")
        if not self.slug:
            source = (
                getattr(self, "name_en", None)
                or getattr(self, "name", None)
                or str(self)
            )
            self.slug = generate_slug(self, source)
        super().save(*args, **kwargs)


class ActiveManager(models.Manager):
    """Manager that only returns active/enabled records."""

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)


def utcnow():
    """Timezone-aware current time helper."""
    return timezone.now()


def normalize_text(value):
    """Normalize unicode text for search comparisons."""
    if not value:
        return ""
    return unicodedata.normalize("NFKD", str(value)).lower()
