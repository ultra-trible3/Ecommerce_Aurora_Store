from django.contrib import admin
from modeltranslation.admin import TranslationAdmin

from .models import (Attribute, AttributeValue, Brand, Category, Product,
                     ProductImage, ProductVariant)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1
    fields = ("name", "sku", "price", "sale_price", "stock_quantity",
              "position", "is_active")


@admin.register(Category)
class CategoryAdmin(TranslationAdmin):
    list_display = ("name", "parent", "is_active", "is_featured", "position")
    list_filter = ("is_active", "is_featured", "parent")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    list_editable = ("position", "is_active", "is_featured")


@admin.register(Brand)
class BrandAdmin(TranslationAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(TranslationAdmin):
    list_display = ("name", "sku", "category", "brand", "price", "sale_price",
                    "stock_quantity", "status", "is_featured")
    list_filter = ("status", "category", "brand", "is_featured",
                   "is_new_arrival", "is_best_seller")
    search_fields = ("name", "sku", "slug", "short_description")
    list_editable = ("price", "sale_price", "stock_quantity", "status",
                     "is_featured")
    readonly_fields = ("rating_average", "rating_count", "sold_count",
                       "view_count", "created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    list_select_related = ("category", "brand")
    inlines = (ProductImageInline, ProductVariantInline)
    fieldsets = (
        (None, {"fields": ("name", "slug", "sku", "status")}),
        ("Classification", {"fields": ("category", "brand")}),
        ("Descriptions", {"fields": ("short_description", "full_description")}),
        ("Pricing", {"fields": ("price", "sale_price", "cost_price")}),
        ("Stock", {"fields": ("stock_quantity", "min_stock_level",
                              "reserved_quantity")}),
        ("Shipping", {"fields": ("weight", "dimensions")}),
        ("Merchandising", {"fields": ("main_image", "is_featured",
                                      "is_new_arrival", "is_best_seller")}),
        ("Performance", {"fields": ("rating_average", "rating_count",
                                    "sold_count", "view_count")}),
        ("SEO", {"fields": ("meta_title", "meta_description",
                            "meta_keywords", "canonical_slug")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )


@admin.register(Attribute)
class AttributeAdmin(TranslationAdmin):
    list_display = ("name", "position")
    list_editable = ("position",)
    search_fields = ("name",)


@admin.register(AttributeValue)
class AttributeValueAdmin(TranslationAdmin):
    list_display = ("attribute", "value", "color_hex", "position")
    list_filter = ("attribute",)
    search_fields = ("value",)
    list_editable = ("position",)


admin.site.register(ProductImage)
admin.site.register(ProductVariant)
