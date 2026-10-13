from modeltranslation.translator import register, TranslationOptions

from .models import Attribute, AttributeValue, Brand, Category, Product, ProductVariant

# Slugs are intentionally NOT translated: URLs have no language prefix, so a
# per-language slug would 404 as soon as the visitor toggled EN <-> AR.


@register(Category)
class CategoryTranslationOptions(TranslationOptions):
    fields = ("name", "description")


@register(Brand)
class BrandTranslationOptions(TranslationOptions):
    fields = ("name", "description")


@register(Product)
class ProductTranslationOptions(TranslationOptions):
    fields = (
        "name",
        "short_description",
        "full_description",
    )


@register(ProductVariant)
class ProductVariantTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Attribute)
class AttributeTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(AttributeValue)
class AttributeValueTranslationOptions(TranslationOptions):
    fields = ("value",)
