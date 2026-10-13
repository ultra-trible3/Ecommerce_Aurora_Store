"""Coupon validation service (server-side, single source of truth)."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.core.utils import money
from .models import Coupon


class CouponService:
    """Validates and applies discount coupons."""

    @staticmethod
    def lookup(code, user=None, subtotal=None, raise_on_error=False):
        """Look up and validate a coupon by code.

        Returns ``(coupon, error_message)``. When ``raise_on_error`` is true
        the ValidationError is raised instead of returned.
        """
        if not code:
            return None, _("Enter a coupon code.")
        coupon = Coupon.objects.filter(code__iexact=code.strip()).first()
        if coupon is None:
            error = _("That coupon code does not exist.")
            if raise_on_error:
                raise ValidationError(error)
            return None, error
        try:
            coupon.validate(user=user, subtotal=subtotal)
        except ValidationError as exc:
            error = "; ".join(exc.messages)
            if raise_on_error:
                raise
            return None, error
        return coupon, None

    @staticmethod
    def apply_to_cart(cart, code, user=None):
        """Validate and store the coupon code on the cart.

        Returns ``(coupon, error)``.
        """
        subtotal = cart.subtotal
        coupon, error = CouponService.lookup(
            code, user=user, subtotal=subtotal
        )
        if error:
            return None, error
        # Scope check: at least one eligible item must exist for
        # product/category-scoped coupons.
        if coupon.scope != Coupon.Scope.ALL:
            eligible = CouponService.eligible_subtotal(cart, coupon)
            if eligible <= 0:
                msg = _(
                    "This coupon does not apply to the items in your cart."
                )
                return None, msg
        cart.coupon_code = coupon.code
        cart.save(update_fields=["coupon_code", "updated_at"])
        return coupon, None

    @staticmethod
    def eligible_subtotal(cart, coupon):
        """Subtotal of cart items this coupon applies to."""
        items = cart.items.select_related("product", "variant")
        if coupon.scope == Coupon.Scope.ALL:
            return money(sum(i.line_total for i in items))

        total = Decimal("0.00")
        if coupon.scope == Coupon.Scope.PRODUCTS:
            product_ids = set(coupon.products.values_list("id", flat=True))
            for item in items:
                if item.product_id in product_ids:
                    total += item.line_total
            return money(total)

        # Category scope: include descendants of every scoped category.
        scoped_ids = set()
        for category in coupon.categories.all():
            scoped_ids.update(
                category.all_descendants.values_list("id", flat=True)
            )
        for item in items:
            item_cat_ids = {item.product.category_id}
            item_cat_ids.update(
                item.product.category.all_descendants.values_list("id", flat=True)
            )
            if item_cat_ids & scoped_ids:
                total += item.line_total
        return money(total)

    @staticmethod
    def clear(cart):
        cart.coupon_code = ""
        cart.save(update_fields=["coupon_code", "updated_at"])
