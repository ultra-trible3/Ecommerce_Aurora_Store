"""Banner/Advertisement models with advanced targeting."""
import json
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.validators import validate_image_file


class Banner(TimeStampedModel):
    """A hero banner/advertisement with targeting and scheduling."""

    class ClickAction(models.TextChoices):
        LINK = "link", _("Navigate to URL")
        MODAL = "modal", _("Open full-screen modal")

    class DeviceTarget(models.TextChoices):
        ALL = "all", _("All devices")
        DESKTOP = "desktop", _("Desktop only")
        MOBILE = "mobile", _("Mobile only")

    class TextAlignment(models.TextChoices):
        LEFT = "left", _("Left")
        CENTER = "center", _("Center")
        RIGHT = "right", _("Right")

    class ButtonStyle(models.TextChoices):
        PRIMARY = "primary", _("Primary")
        OUTLINE = "outline", _("Outline")
        GHOST = "ghost", _("Ghost")

    # Core content
    title = models.CharField(_("title"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=200, unique=True)
    image = models.ImageField(
        _("image"),
        upload_to="banners/%Y/%m/",
        validators=[validate_image_file],
        help_text=_("Main desktop image (recommended 1920x600px)"),
    )
    mobile_image = models.ImageField(
        _("mobile image"),
        upload_to="banners/%Y/%m/",
        blank=True,
        validators=[validate_image_file],
        help_text=_("Optional mobile-specific image (recommended 750x800px)"),
    )

    # Click behavior
    click_action = models.CharField(
        _("click action"),
        max_length=10,
        choices=ClickAction.choices,
        default=ClickAction.LINK,
    )
    link_url = models.URLField(
        _("link URL"),
        blank=True,
        help_text=_("Required when click action is 'Navigate to URL'"),
    )
    modal_content = models.TextField(
        _("modal content"),
        blank=True,
        help_text=_("HTML content for modal (when click action is 'Open full-screen modal')"),
    )
    button_text = models.CharField(
        _("button text"),
        max_length=50,
        blank=True,
        help_text=_("CTA button text (e.g., 'Shop Now', 'Learn More')"),
    )
    button_style = models.CharField(
        _("button style"),
        max_length=10,
        choices=ButtonStyle.choices,
        default=ButtonStyle.PRIMARY,
    )

    # Scheduling
    valid_from = models.DateTimeField(_("valid from"), default=timezone.now)
    valid_until = models.DateTimeField(_("valid until"), null=True, blank=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    # Targeting
    device_target = models.CharField(
        _("device target"),
        max_length=10,
        choices=DeviceTarget.choices,
        default=DeviceTarget.ALL,
    )
    countries = models.JSONField(
        _("countries"),
        default=list,
        blank=True,
        help_text=_("ISO 3166-1 alpha-2 country codes (e.g., ['US', 'CA']). Empty = all countries."),
    )
    user_segments = models.JSONField(
        _("user segments"),
        default=dict,
        blank=True,
        help_text=_("JSON object: {'new_visitors': true, 'returning': false, 'has_orders': true}"),
    )
    min_order_count = models.PositiveIntegerField(
        _("minimum order count"),
        default=0,
        help_text=_("Show only to users with at least this many completed orders"),
    )
    show_once_per_session = models.BooleanField(
        _("show once per session"),
        default=False,
        help_text=_("Use sessionStorage to show banner only once per browser session"),
    )
    is_popup = models.BooleanField(
        _("deal popup"),
        default=False,
        db_index=True,
        help_text=_(
            "Auto-show as a centered deal popup near the top of the page on load "
            "(image only, with a close button)"
        ),
    )

    # Display
    position = models.PositiveIntegerField(
        _("position"),
        default=0,
        help_text=_("Higher values appear first. Used for ordering multiple active banners."),
    )
    overlay_gradient = models.BooleanField(
        _("overlay gradient"),
        default=True,
        help_text=_("Dark gradient overlay for text readability on image"),
    )
    text_alignment = models.CharField(
        _("text alignment"),
        max_length=10,
        choices=TextAlignment.choices,
        default=TextAlignment.LEFT,
    )
    custom_css = models.TextField(
        _("custom CSS"),
        blank=True,
        help_text=_("Additional CSS classes or inline styles for advanced styling"),
    )

    # Analytics
    impressions = models.PositiveIntegerField(_("impressions"), default=0, editable=False)
    clicks = models.PositiveIntegerField(_("clicks"), default=0, editable=False)

    class Meta:
        verbose_name = _("banner")
        verbose_name_plural = _("banners")
        ordering = ("-position", "-created_at")
        indexes = [
            models.Index(fields=["is_active", "valid_from", "valid_until"]),
            models.Index(fields=["position", "-created_at"]),
        ]

    def __str__(self):
        return self.title

    @property
    def is_expired(self):
        return self.valid_until is not None and self.valid_until < timezone.now()

    @property
    def is_started(self):
        return self.valid_from <= timezone.now()

    @property
    def is_scheduled_valid(self):
        return self.is_started and not self.is_expired

    @property
    def ctr(self):
        """Click-through rate as percentage."""
        if self.impressions == 0:
            return Decimal("0.00")
        return Decimal(self.clicks) / Decimal(self.impressions) * Decimal("100")

    def matches_request(self, request, *, skip_session_check=False):
        """Check if this banner matches the given request.

        skip_session_check: ignore the show-once-per-session server flag
        (used for deal popups, which are gated client-side so they can be
        re-armed e.g. after a visitor logs in).
        """
        if not self.is_active or not self.is_scheduled_valid:
            return False

        # Device targeting
        if self.device_target != self.DeviceTarget.ALL:
            is_mobile = getattr(request, "is_mobile", False)
            if self.device_target == self.DeviceTarget.MOBILE and not is_mobile:
                return False
            if self.device_target == self.DeviceTarget.DESKTOP and is_mobile:
                return False

        # Country targeting
        if self.countries:
            country_code = getattr(request, "country_code", None)
            if not country_code or country_code.upper() not in [c.upper() for c in self.countries]:
                return False

        # User segment targeting
        if self.user_segments:
            if not self._matches_user_segments(request):
                return False

        # Minimum order count
        if self.min_order_count > 0:
            if not self._matches_min_orders(request):
                return False

        # Show once per session
        if self.show_once_per_session and not skip_session_check:
            if self._seen_in_session(request):
                return False

        return True

    def _matches_user_segments(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            # Anonymous user - only 'new_visitors' can match
            if self.user_segments.get("new_visitors"):
                return True
            if self.user_segments.get("returning"):
                return False
            if self.user_segments.get("has_orders"):
                return False
            return True

        # Authenticated user
        if self.user_segments.get("has_orders"):
            if not user.orders.filter(status__in=["delivered", "shipped"]).exists():
                return False
        if self.user_segments.get("returning"):
            if user.orders.count() == 0:
                return False
        if self.user_segments.get("new_visitors"):
            if user.orders.count() > 0:
                return False
        return True

    def _matches_min_orders(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        completed = user.orders.filter(status__in=["delivered", "shipped"]).count()
        return completed >= self.min_order_count

    def _seen_in_session(self, request):
        session_key = f"banner_seen_{self.pk}"
        return request.session.get(session_key, False)

    def mark_seen_in_session(self, request):
        session_key = f"banner_seen_{self.pk}"
        request.session[session_key] = True

    def record_impression(self):
        """Increment impression counter (atomic)."""
        Banner.objects.filter(pk=self.pk).update(impressions=models.F("impressions") + 1)

    def record_click(self):
        """Increment click counter (atomic)."""
        Banner.objects.filter(pk=self.pk).update(clicks=models.F("clicks") + 1)

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.click_action == self.ClickAction.LINK and not self.link_url:
            raise ValidationError({"link_url": _("Link URL is required when click action is 'Navigate to URL'.")})
        if self.click_action == self.ClickAction.MODAL and not self.modal_content:
            raise ValidationError({"modal_content": _("Modal content is required when click action is 'Open full-screen modal'.")})
        if self.button_text and self.click_action == self.ClickAction.MODAL and not self.link_url:
            # Button in modal should either close modal or link somewhere
            pass

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)