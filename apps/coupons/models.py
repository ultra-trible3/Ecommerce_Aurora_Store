"""Coupon models and validation service."""
from decimal import Decimal

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.utils import money


class Coupon(TimeStampedModel):
    """A discount coupon with full server-side validation rules."""

    class Type(models.TextChoices):
        PERCENTAGE = "percentage", _("Percentage")
        FIXED = "fixed", _("Fixed amount")
        FREE_SHIPPING = "free_shipping", _("Free shipping")

    class Scope(models.TextChoices):
        ALL = "all", _("Entire order")
        PRODUCTS = "products", _("Specific products")
        CATEGORIES = "categories", _("Specific categories")

    code = models.CharField(max_length=64, unique=True, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.PERCENTAGE)
    value = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text=_("Percentage (0-100) or fixed amount depending on type."),
    )
    scope = models.CharField(
        max_length=20, choices=Scope.choices, default=Scope.ALL
    )
    products = models.ManyToManyField(
        "catalog.Product", related_name="coupons", blank=True
    )
    categories = models.ManyToManyField(
        "catalog.Category", related_name="coupons", blank=True
    )
    min_order_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text=_("Minimum subtotal required."),
    )
    max_discount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_("Cap the discount for percentage coupons."),
    )
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(
        null=True, blank=True, help_text=_("Total uses allowed.")
    )
    used_count = models.PositiveIntegerField(default=0)
    per_user_limit = models.PositiveIntegerField(
        default=1, help_text=_("Uses allowed per customer.")
    )
    is_active = models.BooleanField(default=True, db_index=True)
    applies_to_first_order_only = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("coupon")
        verbose_name_plural = _("coupons")
        ordering = ("-created_at",)

    def __str__(self):
        return self.code

    @property
    def is_expired(self):
        return self.valid_until is not None and self.valid_until < timezone.now()

    @property
    def is_started(self):
        return self.valid_from <= timezone.now()

    @property
    def is_usage_exhausted(self):
        return self.usage_limit is not None and self.used_count >= self.usage_limit

    @property
    def times_used(self):
        return self.used_count

    @property
    def discount_label(self):
        if self.type == self.Type.PERCENTAGE:
            return _("{}% off").format(self.value)
        if self.type == self.Type.FIXED:
            return _("{} off").format(money(self.value))
        return _("Free shipping")

    # ------------------------------------------------------------------
    # Server-side validation
    # ------------------------------------------------------------------
    def validate(self, user=None, subtotal=None):
        """Validate this coupon against a user and/or cart subtotal.

        Raises ``ValidationError`` with a helpful message when invalid.
        Returns ``None`` when valid.
        """
        from django.core.exceptions import ValidationError

        if not self.is_active:
            raise ValidationError(_("This coupon is no longer active."))
        if not self.is_started:
            raise ValidationError(_("This coupon is not active yet."))
        if self.is_expired:
            raise ValidationError(_("This coupon has expired."))
        if self.is_usage_exhausted:
            raise ValidationError(_("This coupon has reached its usage limit."))

        if subtotal is not None and self.min_order_amount:
            if Decimal(subtotal) < self.min_order_amount:
                raise ValidationError(
                    _("A minimum order of %(amount)s is required for this coupon.")
                    % {"amount": money(self.min_order_amount)}
                )

        if user is not None and user.is_authenticated:
            used_by_user = self.redemptions.filter(user=user).count()
            if used_by_user >= self.per_user_limit:
                raise ValidationError(_("You have already used this coupon."))
            if self.applies_to_first_order_only and self.redemptions.filter(
                user=user
            ).exists():
                raise ValidationError(
                    _("This coupon is valid for first-time orders only.")
                )
        elif self.applies_to_first_order_only:
            raise ValidationError(
                _("Sign in to use this first-order coupon.")
            )
        return None

    def compute_discount(self, subtotal, shipping=Decimal("0.00"), eligible_amount=None):
        """Compute the discount for a given subtotal.

        ``eligible_amount`` limits the base used for scope-limited coupons.
        """
        subtotal = Decimal(subtotal)
        shipping = Decimal(shipping)
        if self.type == self.Type.FREE_SHIPPING:
            return money(shipping)
        base = Decimal(eligible_amount) if eligible_amount is not None else subtotal
        if self.type == self.Type.PERCENTAGE:
            rate = min(max(self.value, 0), 100) / Decimal("100")
            discount = base * Decimal(str(rate))
            if self.max_discount is not None:
                discount = min(discount, self.max_discount)
        else:  # fixed
            discount = min(self.value, base)
        return money(max(discount, Decimal("0.00")))
