from django.contrib import admin

from .models import Coupon


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "type", "discount_label", "scope",
                    "valid_from", "valid_until", "used_count", "usage_limit",
                    "is_active")
    list_filter = ("type", "scope", "is_active",
                   "applies_to_first_order_only")
    search_fields = ("code", "description")
    list_editable = ("is_active",)
    filter_horizontal = ("products", "categories")
    readonly_fields = ("used_count", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("code", "description", "type", "value", "scope",
                           "is_active")}),
        ("Restrictions", {"fields": ("products", "categories",
                                     "min_order_amount", "max_discount")}),
        ("Validity", {"fields": ("valid_from", "valid_until")}),
        ("Limits", {"fields": ("usage_limit", "used_count", "per_user_limit",
                               "applies_to_first_order_only")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
