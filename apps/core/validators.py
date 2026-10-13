"""Reusable validators for uploads and form fields."""
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def validate_image_file(value):
    """Validate image extension and size before saving."""
    ext = os.path.splitext(value.name)[1].lower()
    allowed = getattr(
        settings, "ALLOWED_IMAGE_EXTENSIONS", [".jpg", ".jpeg", ".png", ".webp", ".gif"]
    )
    if ext and ext not in allowed:
        raise ValidationError(
            _("Unsupported file type '%(ext)s'. Allowed: %(allowed)s.")
            % {"ext": ext, "allowed": ", ".join(allowed)}
        )
    max_size = getattr(settings, "MAX_IMAGE_SIZE", 5 * 1024 * 1024)
    if hasattr(value, "size") and value.size > max_size:
        raise ValidationError(
            _("File is too large (max %(max_mb)s MB).")
            % {"max_mb": max_size // (1024 * 1024)}
        )


def validate_phone(value):
    """Allow digits, spaces, +, -, (, ) in phone numbers."""
    cleaned = "".join(ch for ch in str(value) if ch.isdigit())
    if len(cleaned) < 7 or len(cleaned) > 15:
        raise ValidationError(_("Enter a valid phone number (7-15 digits)."))
