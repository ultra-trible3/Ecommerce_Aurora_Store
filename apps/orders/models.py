"""Order models with historical snapshots and status tracking."""
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.utils import money


class ShippingZone(models.Model):
    """A geographical zone for shipping rate calculations."""
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    countries = models.JSONField(
        default=list,
        help_text=_("List of ISO country codes (e.g., ['US', 'CA'])")
    )
    states = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of state/province codes (optional, e.g., ['CA', 'NY'])")
    )
    postal_codes = models.JSONField(
        default=list,
        blank=True,
        help_text=_("List of postal code prefixes (optional, e.g., ['90', '100'])")
    )
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ("position", "name")
        verbose_name = _("shipping zone")
        verbose_name_plural = _("shipping zones")
    
    def __str__(self):
        return self.name
    
    def matches(self, country, state="", postal_code=""):
        """Check if an address matches this zone."""
        country = country.upper().strip() if country else ""
        if country not in [c.upper() for c in self.countries]:
            return False
        if self.states:
            state = state.upper().strip() if state else ""
            if state not in [s.upper() for s in self.states]:
                return False
        if self.postal_codes:
            postal = postal_code.upper().strip() if postal_code else ""
            if not any(postal.startswith(p.upper()) for p in self.postal_codes):
                return False
        return True


class ShippingMethod(models.Model):
    """An admin-managed delivery option shown at checkout."""
    
    class CalculationType(models.TextChoices):
        FLAT_RATE = "flat_rate", _("Flat rate per order")
        WEIGHT_BASED = "weight_based", _("Based on order weight")
        PRICE_BASED = "price_based", _("Based on order subtotal")
        FREE = "free", _("Always free")
    
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=255, blank=True)
    calculation_type = models.CharField(
        max_length=20, choices=CalculationType.choices, default=CalculationType.FLAT_RATE
    )
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    free_over = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_("Free when subtotal reaches this amount (flat_rate only)."),
    )
    # Weight-based settings
    base_weight = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        help_text=_("Base weight in kg for weight-based calculation")
    )
    weight_rate = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text=_("Cost per kg over base_weight")
    )
    # Zone-based rates (optional)
    zones = models.ManyToManyField(
        ShippingZone, related_name="shipping_methods", blank=True,
        help_text=_("Restrict this method to specific zones")
    )
    estimated_days = models.CharField(max_length=50, blank=True, default="3-5 days")
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ("position", "name")
    
    def __str__(self):
        return self.name
    
    @property
    def requires_payment(self):
        return self.code != "cod"
    
    def price_for(self, subtotal, weight=0, zone=None):
        """
        Calculate shipping price for given order parameters.
        
        Args:
            subtotal: Order subtotal
            weight: Total order weight in kg
            zone: ShippingZone instance or None
        """
        subtotal = money(subtotal)
        
        # Check free_over threshold
        if self.calculation_type == self.CalculationType.FLAT_RATE:
            if self.free_over is not None and subtotal >= money(self.free_over):
                return money(0)
            return money(self.cost)
        
        elif self.calculation_type == self.CalculationType.WEIGHT_BASED:
            weight = float(weight) if weight else 0
            base = float(self.base_weight) if self.base_weight else 0
            rate = float(self.weight_rate) if self.weight_rate else 0
            if weight <= base:
                return money(0)
            return money((weight - base) * rate)
        
        elif self.calculation_type == self.CalculationType.PRICE_BASED:
            return money(self.cost)  # Could add percentage logic here
        
        elif self.calculation_type == self.CalculationType.FREE:
            return money(0)
        
        return money(self.cost)
    
    def is_available_for(self, country, state="", postal_code=""):
        """Check if this shipping method is available for the given address."""
        if not self.is_active:
            return False
        if not self.zones.exists():
            return True  # Available everywhere if no zones specified
        for zone in self.zones.all():
            if zone.is_active and zone.matches(country, state, postal_code):
                return True
        return False
    
    def get_zone_rate(self, country, state="", postal_code=""):
        """Get the shipping rate for a specific zone (if zone-based pricing)."""
        if not self.zones.exists():
            return None
        for zone in self.zones.all():
            if zone.is_active and zone.matches(country, state, postal_code):
                # Could extend with zone-specific rates in the future
                return self.price_for(0)
        return None


class ShippingRate(models.Model):
    """Zone-specific rate override for a shipping method."""
    
    shipping_method = models.ForeignKey(
        ShippingMethod, on_delete=models.CASCADE, related_name="rates"
    )
    zone = models.ForeignKey(
        ShippingZone, on_delete=models.CASCADE, related_name="rates"
    )
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    free_over = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_("Free when subtotal reaches this amount in this zone.")
    )
    
    class Meta:
        unique_together = ("shipping_method", "zone")
        verbose_name = _("shipping rate")
        verbose_name_plural = _("shipping rates")
    
    def __str__(self):
        return f"{self.shipping_method.name} → {self.zone.name}: {self.cost}"
    
    def price_for(self, subtotal, weight=0):
        """Calculate rate for this specific zone."""
        subtotal = money(subtotal)
        if self.free_over is not None and subtotal >= money(self.free_over):
            return money(0)
        return money(self.cost)


class Order(TimeStampedModel):
    """A customer order with denormalized address and totals snapshots."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        PROCESSING = "processing", _("Processing")
        PACKED = "packed", _("Packed")
        SHIPPED = "shipped", _("Shipped")
        OUT_FOR_DELIVERY = "out_for_delivery", _("Out for delivery")
        DELIVERED = "delivered", _("Delivered")
        CANCELLED = "cancelled", _("Cancelled")
        RETURNED = "returned", _("Returned")
        REFUNDED = "refunded", _("Refunded")

    ACTIVE_STATUSES = (
        Status.PENDING, Status.CONFIRMED, Status.PROCESSING, Status.PACKED,
        Status.SHIPPED, Status.OUT_FOR_DELIVERY,
    )
    CANCELLABLE_STATUSES = (Status.PENDING, Status.CONFIRMED)
    FULFILMENT_STATUSES = (
        Status.CONFIRMED, Status.PROCESSING, Status.PACKED, Status.SHIPPED,
        Status.OUT_FOR_DELIVERY, Status.DELIVERED,
    )
    FULFILMENT_FLOW = (
        Status.PENDING, Status.CONFIRMED, Status.PROCESSING, Status.PACKED,
        Status.SHIPPED, Status.OUT_FOR_DELIVERY, Status.DELIVERED,
    )
    DEAD_END_STATUSES = (Status.CANCELLED, Status.RETURNED, Status.REFUNDED)

    order_number = models.CharField(max_length=32, unique=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    email = models.EmailField()
    guest_name = models.CharField(max_length=150, blank=True)
    guest_phone = models.CharField(max_length=30, blank=True)

    # Denormalized address snapshots (immutable history)
    shipping_full_name = models.CharField(max_length=150)
    shipping_phone = models.CharField(max_length=30, blank=True)
    shipping_address_line1 = models.CharField(max_length=255)
    shipping_address_line2 = models.CharField(max_length=255, blank=True)
    shipping_city = models.CharField(max_length=100)
    shipping_state = models.CharField(max_length=100, blank=True)
    shipping_country = models.CharField(max_length=100, default=_("United States"))
    shipping_postal_code = models.CharField(max_length=20)

    billing_full_name = models.CharField(max_length=150, blank=True)
    billing_phone = models.CharField(max_length=30, blank=True)
    billing_address_line1 = models.CharField(max_length=255, blank=True)
    billing_address_line2 = models.CharField(max_length=255, blank=True)
    billing_city = models.CharField(max_length=100, blank=True)
    billing_state = models.CharField(max_length=100, blank=True)
    billing_country = models.CharField(max_length=100, blank=True)
    billing_postal_code = models.CharField(max_length=20, blank=True)
    same_as_shipping = models.BooleanField(default=True)

    shipping_method_name = models.CharField(max_length=100, blank=True)
    shipping_method_code = models.CharField(max_length=50, blank=True)
    shipping_method_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0
    )

    payment_method = models.CharField(max_length=30, default="cod")
    payment_status = models.CharField(
        max_length=20,
        choices=[
            ("pending", _("Pending")),
            ("processing", _("Processing")),
            ("paid", _("Paid")),
            ("failed", _("Failed")),
            ("refunded", _("Refunded")),
            ("cancelled", _("Cancelled")),
        ],
        default="pending",
        db_index=True,
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    coupon_code = models.CharField(max_length=64, blank=True)
    coupon = models.ForeignKey(
        "coupons.Coupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    cancel_reason = models.CharField(max_length=255, blank=True)
    cancel_reason_category = models.CharField(max_length=50, blank=True,
        help_text=_("Category of cancellation reason for analytics"))

    cancelled_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["payment_status", "-created_at"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["email"]),
            models.Index(fields=["order_number"]),
            models.Index(fields=["status", "payment_status", "-created_at"]),
        ]

    def __str__(self):
        return self.order_number

    @property
    def is_paid(self):
        return self.payment_status == "paid"

    @property
    def can_cancel(self):
        """
        Check if order can be cancelled by customer.
        
        Rules:
        - Status must be in CANCELLABLE_STATUSES (PENDING, CONFIRMED)
        - Order must not be paid (except COD which can be cancelled before shipped)
        - Must be within cancellation window (if configured)
        """
        if self.status not in self.CANCELLABLE_STATUSES:
            return False
        
        # COD orders can be cancelled anytime before shipped (even if marked paid on delivery)
        if self.payment_method == "cod":
            return self.status not in (self.Status.SHIPPED, self.Status.OUT_FOR_DELIVERY, 
                                        self.Status.DELIVERED)
        
        # Paid orders cannot be cancelled by customer
        if self.is_paid:
            return False
        
        # Check cancellation time window
        from django.conf import settings
        window = getattr(settings, "CANCELLATION_WINDOW_MINUTES", 30)
        if window > 0:
            from django.utils import timezone
            from datetime import timedelta
            if self.created_at:
                expiry = self.created_at + timedelta(minutes=window)
                if timezone.now() > expiry:
                    return False
        
        return True

    @property
    def can_cancel_admin(self):
        """
        Admin can cancel orders in more states:
        - Any active status (PENDING through OUT_FOR_DELIVERY)
        - Even paid orders (will trigger refund)
        - But not DELIVERED, RETURNED, REFUNDED, CANCELLED
        """
        return self.status in self.ACTIVE_STATUSES

    # Cancellation reason categories for analytics
    CANCEL_REASON_CATEGORIES = [
        ("changed_mind", _("Changed mind")),
        ("found_better_price", _("Found better price elsewhere")),
        ("delivery_too_slow", _("Delivery takes too long")),
        ("order_mistake", _("Ordered by mistake / wrong item")),
        ("payment_issue", _("Payment issues")),
        ("address_issue", _("Address / delivery issues")),
        ("other", _("Other")),
    ]

    @property
    def progress_percent(self):
        """Where this order sits on the fulfilment timeline (0-100)."""
        if self.status in self.DEAD_END_STATUSES:
            return 100
        try:
            index = self.FULFILMENT_FLOW.index(self.status)
        except ValueError:
            return 0
        return round((index + 1) * 100 / len(self.FULFILMENT_FLOW))

    @property
    def items_count(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def shipping_address_line(self):
        parts = [
            self.shipping_address_line1, self.shipping_address_line2,
            self.shipping_city, self.shipping_state,
            self.shipping_postal_code, self.shipping_country,
        ]
        return ", ".join(str(p) for p in parts if p)

    @property
    def billing_address_line(self):
        if self.same_as_shipping:
            return self.shipping_address_line
        parts = [
            self.billing_address_line1, self.billing_address_line2,
            self.billing_city, self.billing_state,
            self.billing_postal_code, self.billing_country,
        ]
        return ", ".join(str(p) for p in parts if p)

    @property
    def customer_name(self):
        if self.user:
            return self.user.get_full_name() or self.user.email
        return self.guest_name or self.shipping_full_name

    @property
    def tracking_steps(self):
        """Ordered tracking timeline including timestamps."""
        timeline = {
            h.to_status: h.created_at for h in self.status_history.all()
        }
        order_flow = [
            (self.Status.PENDING, _("Order placed")),
            (self.Status.CONFIRMED, _("Confirmed")),
            (self.Status.PROCESSING, _("Processing")),
            (self.Status.PACKED, _("Packed")),
            (self.Status.SHIPPED, _("Shipped")),
            (self.Status.OUT_FOR_DELIVERY, _("Out for delivery")),
            (self.Status.DELIVERED, _("Delivered")),
        ]
        if self.status == self.Status.PENDING:
            current_index = 0
        else:
            keys = [s for s, _ in order_flow]
            current_index = (
                keys.index(self.status) if self.status in keys else -1
            )
        steps = []
        for index, (code, label) in enumerate(order_flow):
            steps.append({
                "code": code,
                "label": label,
                "timestamp": timeline.get(code),
                "done": current_index >= index,
                "current": current_index == index,
            })
        if self.status in (self.Status.CANCELLED, self.Status.REFUNDED,
                           self.Status.RETURNED):
            steps.append({
                "code": self.status,
                "label": self.get_status_display(),
                "timestamp": timeline.get(self.status),
                "done": True,
                "current": True,
            })
        return steps


class OrderItem(models.Model):
    """Immutable historical snapshot of a purchased line item."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )
    # Snapshot fields
    product_name = models.CharField(max_length=255)
    product_slug = models.CharField(max_length=255, blank=True)
    product_sku = models.CharField(max_length=64)
    variant_name = models.CharField(max_length=150, blank=True)
    image_url = models.CharField(max_length=500, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=1)
    line_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ("id",)

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"

    @property
    def display_name(self):
        if self.variant_name:
            return f"{self.product_name} ({self.variant_name})"
        return self.product_name

    @property
    def discount_each(self):
        return money(max(self.original_price - self.unit_price, 0))

    @property
    def discount_amount(self):
        return money(self.discount_each * self.quantity)


class OrderStatusHistory(models.Model):
    """Audit trail of every order status change."""

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="status_history"
    )
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    note = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_events",
    )
    is_customer_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        verbose_name = _("order status history")

    def __str__(self):
        return f"{self.order.order_number}: {self.from_status} → {self.to_status}"

    @property
    def label(self):
        order = Order.Status(self.to_status)
        return order.label if order else self.to_status


class CouponRedemption(models.Model):
    """Records each successful coupon usage against an order."""

    coupon = models.ForeignKey(
        "coupons.Coupon", on_delete=models.CASCADE, related_name="redemptions"
    )
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="coupon_redemptions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupon_redemptions",
    )
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.coupon.code} → {self.order.order_number}"


class ReturnRequest(models.Model):
    """Customer return/refund request with admin approval workflow."""
    
    class Status(models.TextChoices):
        REQUESTED = "requested", _("Requested")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        RECEIVED = "received", _("Received at warehouse")
        REFUNDED = "refunded", _("Refunded")
        CANCELLED = "cancelled", _("Cancelled by customer")
    
    class Reason(models.TextChoices):
        DEFECTIVE = "defective", _("Defective / damaged")
        WRONG_ITEM = "wrong_item", _("Wrong item sent")
        NOT_AS_DESCRIBED = "not_as_described", _("Not as described")
        CHANGED_MIND = "changed_mind", _("Changed mind")
        SIZE_FIT = "size_fit", _("Size / fit issues")
        LATE_DELIVERY = "late_delivery", _("Late delivery")
        OTHER = "other", _("Other")
    
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="return_requests"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="return_requests"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.REQUESTED, db_index=True
    )
    reason = models.CharField(max_length=20, choices=Reason.choices)
    reason_detail = models.TextField(blank=True)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    admin_note = models.TextField(blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    carrier = models.CharField(max_length=100, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("return request")
        verbose_name_plural = _("return requests")
    
    def __str__(self):
        return _("Return #%(pk)s for %(order)s (%(status)s)") % {
            "pk": self.pk,
            "order": self.order.order_number,
            "status": self.get_status_display(),
        }
    
    @property
    def can_customer_cancel(self):
        return self.status in (self.Status.REQUESTED, self.Status.APPROVED)
    
    @property
    def is_final(self):
        return self.status in (self.Status.REFUNDED, self.Status.REJECTED, self.Status.CANCELLED)
    
    def calculate_refund_amount(self):
        """Calculate total refund based on items in this return."""
        total = sum(item.refund_amount for item in self.items.all())
        self.refund_amount = total
        self.save(update_fields=["refund_amount"])
        return total


class ReturnItem(models.Model):
    """Individual items within a return request."""
    
    return_request = models.ForeignKey(
        ReturnRequest, on_delete=models.CASCADE, related_name="items"
    )
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.CASCADE, related_name="return_items"
    )
    quantity = models.PositiveIntegerField(default=1)
    reason = models.CharField(max_length=20, choices=ReturnRequest.Reason.choices)
    reason_detail = models.TextField(blank=True)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    restock = models.BooleanField(default=True)
    
    class Meta:
        ordering = ("id",)
    
    def __str__(self):
        return _("%(qty)s × %(name)s (Return #%(pk)s)") % {
            "qty": self.quantity,
            "name": self.order_item.product_name,
            "pk": self.return_request.pk,
        }
    
    def save(self, *args, **kwargs):
        # Auto-calculate refund amount based on order item price
        if not self.refund_amount:
            self.refund_amount = self.order_item.unit_price * self.quantity
        super().save(*args, **kwargs)
        # Update parent return request total
        self.return_request.calculate_refund_amount()
