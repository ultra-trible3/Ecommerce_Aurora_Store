from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import CouponRedemption, Order, OrderItem, OrderStatusHistory, ShippingMethod


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    fields = ("product_name", "product_sku", "variant_name", "unit_price",
              "quantity", "line_total")
    readonly_fields = fields


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    can_delete = False
    ordering = ("-created_at",)
    readonly_fields = ("from_status", "to_status", "note", "actor",
                       "is_customer_visible", "created_at")


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "cost", "free_over", "estimated_days",
                    "is_active", "position")
    list_editable = ("cost", "is_active", "position")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "description")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "customer", "status", "payment_status",
                    "payment_method", "total", "placed")
    list_filter = ("status", "payment_status", "payment_method", "created_at")
    search_fields = ("order_number", "email", "guest_name",
                     "shipping_full_name", "shipping_postal_code")
    list_select_related = ("user", "coupon")
    date_hierarchy = "created_at"
    inlines = (OrderItemInline, OrderStatusHistoryInline)
    readonly_fields = (
        "order_number", "user", "email", "guest_name", "guest_phone",
        "shipping_full_name", "shipping_phone", "shipping_address_line1",
        "shipping_address_line2", "shipping_city", "shipping_state",
        "shipping_country", "shipping_postal_code",
        "billing_full_name", "billing_phone", "billing_address_line1",
        "billing_address_line2", "billing_city", "billing_state",
        "billing_country", "billing_postal_code", "same_as_shipping",
        "shipping_method_name", "shipping_method_code",
        "shipping_method_price",
        "subtotal", "discount", "tax", "shipping_cost", "total",
        "coupon_code", "delivered_at", "created_at", "updated_at",
    )
    fieldsets = (
        (_("Order"), {"fields": ("order_number", "user", "email", "guest_name",
                                 "guest_phone", "created_at")}),
        (_("Status"), {"fields": (("status", "payment_status"), "payment_method",
                                  "delivered_at")}),
        (_("Shipping address"), {
            "classes": ("collapse",),
            "fields": ("shipping_full_name", "shipping_phone",
                       "shipping_address_line1", "shipping_address_line2",
                       "shipping_city", "shipping_state", "shipping_country",
                       "shipping_postal_code"),
        }),
        (_("Billing address"), {
            "classes": ("collapse",),
            "fields": ("same_as_shipping", "billing_full_name", "billing_phone",
                       "billing_address_line1", "billing_address_line2",
                       "billing_city", "billing_state", "billing_country",
                       "billing_postal_code"),
        }),
        (_("Delivery"), {"fields": ("shipping_method_name", "shipping_method_code",
                                    "shipping_method_price")}),
        (_("Totals"), {"fields": ("subtotal", "discount", "tax", "shipping_cost",
                                  "total", "coupon", "coupon_code")}),
        (_("Notes"), {"fields": ("notes", "internal_notes", "cancel_reason",
                                 "updated_at")}),
    )

    @admin.display(description=_("Customer"))
    def customer(self, obj):
        return obj.customer_name

    @admin.display(description=_("Placed"))
    def placed(self, obj):
        return obj.created_at


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ("coupon", "order", "user", "discount_amount", "created_at")
    list_filter = ("coupon", "created_at")
    search_fields = ("coupon__code", "order__order_number", "user__email")
    readonly_fields = ("coupon", "order", "user", "discount_amount", "created_at")
