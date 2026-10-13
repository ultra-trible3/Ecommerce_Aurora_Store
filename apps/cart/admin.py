from django.contrib import admin

from .models import Cart, CartItem, WishlistItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    raw_id_fields = ("product", "variant")


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "coupon_code", "updated_at")
    search_fields = ("user__email", "session_key", "coupon_code")
    list_filter = ("coupon_code",)
    list_select_related = ("user",)
    inlines = (CartItemInline,)


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "created_at")
    search_fields = ("user__email", "product__name", "product__sku")
    list_select_related = ("user", "product")
