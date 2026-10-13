"""Cart and wishlist models."""
from django.conf import settings
from django.db import models

from apps.catalog.models import Product, ProductVariant
from apps.core.utils import money


class Cart(models.Model):
    """A cart owned either by a logged-in user or an anonymous session."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cart",
    )
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    coupon_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["session_key", "-updated_at"]),
        ]

    def __str__(self):
        owner = self.user.email if self.user else f"guest:{self.session_key[:8]}"
        return f"Cart({owner})"

    @property
    def is_empty(self):
        return not self.items.exists()

    @property
    def subtotal(self):
        return money(sum(item.line_total for item in self.items.all()))

    @property
    def total_quantity(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def item_count(self):
        return self.items.count()

    @property
    def total_weight(self):
        """Total weight of all items in kg."""
        return sum(item.weight for item in self.items.all())

    @property
    def has_out_of_stock_items(self):
        return any(not item.is_available for item in self.items.all())

    @property
    def valid_items(self):
        """Items that can still be purchased (stock available)."""
        return [item for item in self.items.select_related("product", "variant")
                if item.is_available]

    @property
    def coupon(self):
        if not self.coupon_code:
            return None
        from apps.coupons.models import Coupon

        try:
            return Coupon.objects.get(code__iexact=self.coupon_code)
        except Coupon.DoesNotExist:
            return None

    def clear(self):
        self.items.all().delete()
        self.coupon_code = ""
        self.save(update_fields=["coupon_code", "updated_at"])


class CartItem(models.Model):
    """A line item inside a cart. Prices are re-validated on every read."""

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="cart_items"
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-added_at",)
        unique_together = ("cart", "product", "variant")

    def __str__(self):
        return f"{self.quantity} × {self.product.name}"

    @property
    def unit_price(self):
        """Current price straight from the database (never from the client)."""
        if self.variant:
            return money(self.variant.current_price)
        return money(self.product.current_price)

    @property
    def base_unit_price(self):
        if self.variant:
            return money(self.variant.base_price)
        return money(self.product.price)

    @property
    def line_total(self):
        return money(self.unit_price * self.quantity)

    @property
    def line_base_total(self):
        return money(self.base_unit_price * self.quantity)

    @property
    def is_on_sale(self):
        if self.variant:
            return self.variant.is_on_sale
        return self.product.is_on_sale

    @property
    def is_available(self):
        """Product/variant must still exist, be active and have stock."""
        if not self.product_id or self.product.status != Product.Status.ACTIVE:
            return False
        available = (
            self.variant.available_quantity if self.variant else self.product.available_quantity
        )
        return available >= self.quantity and self.quantity > 0

    @property
    def weight(self):
        """Total weight of this line item in kg.

        Variants inherit their product's weight — ``ProductVariant`` carries no
        weight of its own.
        """
        item_weight = (
            float(self.product.weight) if self.product.weight is not None else 0.0
        )
        return item_weight * self.quantity
    
    @property
    def max_quantity(self):
        if self.variant:
            return self.variant.available_quantity
        return self.product.available_quantity

    @property
    def display_name(self):
        if self.variant:
            return f"{self.product.name} ({self.variant.name})"
        return self.product.name

    @property
    def image_url(self):
        if self.variant and self.product.main_image:
            return self.product.main_image.url
        return self.product.main_image.url if self.product.main_image else ""


class WishlistItem(models.Model):
    """A saved product on a user's wishlist."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="wishlist_items"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        unique_together = ("user", "product")
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self):
        return f"{self.user} ♥ {self.product.name}"

    @property
    def in_stock(self):
        return self.product.is_in_stock
