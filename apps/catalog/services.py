"""Catalog query/filter service for the storefront."""
import re

from django.db.models import Count, Max, Min, Q
from django.utils.text import slugify
from django.utils.translation import gettext as _

from apps.core.models import ActiveManager, sync_default_language
from apps.core.utils import money

from .models import (
    Attribute,
    AttributeValue,
    Brand,
    Category,
    Product,
    ProductVariant,
)


RECENTLY_VIEWED_KEY = "recently_viewed"
RECENTLY_VIEWED_MAX = 20


def get_recently_viewed(request):
    """Get recently viewed product slugs from session."""
    if not hasattr(request, "session"):
        return []
    slugs = request.session.get(RECENTLY_VIEWED_KEY, [])
    if not isinstance(slugs, list):
        return []
    return slugs[-RECENTLY_VIEWED_MAX:]


def add_to_recently_viewed(request, product_slug):
    """Add a product to recently viewed list in session."""
    slugs = get_recently_viewed(request)
    if product_slug in slugs:
        slugs.remove(product_slug)
    slugs.insert(0, product_slug)
    request.session[RECENTLY_VIEWED_KEY] = slugs[:RECENTLY_VIEWED_MAX]
    request.session.modified = True


def get_recently_viewed_products(request, limit=4):
    """Get recently viewed product objects."""
    slugs = get_recently_viewed(request)
    if not slugs:
        return []
    from .models import Product
    products = list(Product.objects.active().filter(slug__in=slugs).select_related("category", "brand"))
    products.sort(key=lambda p: slugs.index(p.slug))
    return products[:limit]


SORT_CHOICES = {
    "newest": ("-created_at",),
    "price_asc": ("price",),
    "price_desc": ("-price",),
    "popular": ("-sold_count", "-created_at",),
    "rating": ("-rating_average", "-rating_count",),
    "discount": ("-created_at",),  # refined below with annotate
}

BRAND_SEPARATOR = ","


def _active_filters(request):
    """Human-readable labels of the filters currently applied."""
    labels = []
    params = request.GET
    if params.get("q"):
        labels.append(("q", _('Search: "%(query)s"') % {"query": params.get("q")}))
    if params.get("category"):
        labels.append(("category", _("Category: %(category)s") % {"category": params.get("category")}))
    if params.get("brand"):
        labels.append(("brand", _("Brand: %(brand)s") % {"brand": params.get("brand")}))
    if params.get("min_price") or params.get("max_price"):
        low = params.get("min_price") or "0"
        high = params.get("max_price")
        text = _("Price: $%(low)s") % {"low": low} + (
            _(" \u2013 $%(high)s") % {"high": high} if high else "+"
        )
        labels.append(("price", text))
    if params.get("rating"):
        labels.append(("rating", _("Rating: %(rating)s\u2605 & up") % {"rating": params.get("rating")}))
    if params.get("color"):
        labels.append(("color", _("Color: %(color)s") % {"color": params.get("color_name", "")}))
    if params.get("size"):
        labels.append(("size", _("Size: %(size)s") % {"size": params.get("size_name", "")}))
    if params.get("sale") == "1":
        labels.append(("sale", _("On sale")))
    if params.get("featured") == "1":
        labels.append(("featured", _("Featured")))
    if params.get("in_stock") == "1":
        labels.append(("in_stock", _("In stock")))
    if params.get("new") == "1":
        labels.append(("new", _("New arrivals")))
    return labels


def filter_products(request, queryset=None):
    """Apply search/filter/sort querystring params to a product queryset."""
    qs = queryset if queryset is not None else Product.objects.active()
    qs = qs.select_related("category", "brand")
    params = request.GET

    q = (params.get("q") or "").strip()
    if q:
        qs = qs.search(q)

    category_slug = params.get("category")
    if category_slug:
        category = Category.objects.filter(slug=category_slug).first()
        if category:
            # Include descendants of the selected category.
            ids = category.all_descendants.values_list("id", flat=True)
            qs = qs.filter(category_id__in=list(ids))

    brand_param = (params.get("brand") or "").strip()
    if brand_param:
        slugs = [s for s in brand_param.split(BRAND_SEPARATOR) if s]
        if slugs:
            qs = qs.filter(brand__slug__in=slugs)

    min_price = params.get("min_price")
    max_price = params.get("max_price")
    if min_price:
        try:
            qs = qs.filter(price__gte=float(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            qs = qs.filter(price__lte=float(max_price))
        except ValueError:
            pass

    rating = params.get("rating")
    if rating:
        try:
            qs = qs.filter(rating_average__gte=float(rating))
        except ValueError:
            pass

    if params.get("sale") == "1":
        qs = qs.on_sale()
    if params.get("featured") == "1":
        qs = qs.filter(is_featured=True)
    if params.get("new") == "1":
        qs = qs.filter(is_new_arrival=True)
    if params.get("in_stock") == "1":
        qs = qs.filter(stock_quantity__gt=0)

    color = params.get("color")
    if color:
        try:
            qs = qs.filter(
                variants__attributes__pk=int(color),
                variants__is_active=True,
            ).distinct()
        except ValueError:
            pass

    size = params.get("size")
    if size:
        try:
            qs = qs.filter(
                variants__attributes__pk=int(size),
                variants__is_active=True,
            ).distinct()
        except ValueError:
            pass

    sort = params.get("sort", "newest")
    if sort == "discount":
        from django.db.models import F, Value, DecimalField
        from django.db.models.functions import Coalesce, NullIf

        qs = qs.annotate(
            _discount=(
                (F("price") - Coalesce(F("sale_price"), F("price")))
                / NullIf(F("price"), Value(0, output_field=DecimalField()))
            )
        ).order_by("-_discount", "-created_at")
    else:
        ordering = SORT_CHOICES.get(sort, SORT_CHOICES["newest"])
        qs = qs.order_by(*ordering)

    return qs


def shop_context(request):
    """Facet data used by the filter sidebar."""
    colors = AttributeValue.objects.filter(
        Q(attribute__name_en__iexact="color")
        | Q(attribute__name_ar__iexact="color"),
        variants__is_active=True,
    ).distinct().order_by("position")
    sizes = AttributeValue.objects.filter(
        Q(attribute__name_en__iexact="size")
        | Q(attribute__name_ar__iexact="size"),
        variants__is_active=True,
    ).distinct().order_by("position")

    brands = (
        Brand.objects.filter(is_active=True, products__status=Product.Status.ACTIVE)
        .distinct()
        .order_by("name")
    )
    price_range = Product.objects.active().aggregate(
        min_price=Min("price"), max_price=Max("price"),
    )
    return {
        "colors": colors,
        "sizes": sizes,
        "brands": brands,
        "price_min": money(price_range["min_price"] or 0),
        "price_max": money(price_range["max_price"] or 0),
        "active_filters": _active_filters(request),
        "current_brand_list": [
            s for s in (request.GET.get("brand") or "").split(",") if s
        ],
    }


def search_products(query, limit=6):
    """Lightweight autocomplete results."""
    if not query:
        return Product.objects.none()
    return (
        Product.objects.active()
        .search(query)
        .select_related("category", "brand")
        .order_by("-sold_count", "-created_at")[:limit]
    )


def related_products(product, limit=4):
    """Products from the same category (excluding itself), then fallback."""
    related = (
        Product.objects.active()
        .filter(category=product.category)
        .exclude(pk=product.pk)
        .select_related("category", "brand")
        .order_by("-rating_average", "-sold_count")[:limit]
    )
    if related.count() < limit:
        extra = (
            Product.objects.active()
            .exclude(pk=product.pk)
            .exclude(pk__in=[p.pk for p in related])
            .filter(
                Q(category=product.category)
                | Q(brand=product.brand)
                | Q(is_best_seller=True)
            )
            .select_related("category", "brand")
            .order_by("-sold_count")[: limit - related.count()]
        )
        related = list(related) + list(extra)
    return related


def frequently_bought_together(product, limit=4):
    """Products most often purchased in the same orders as ``product``.

    Counts co-occurrence across order line items, then returns the live
    products ordered by how frequently they appear alongside this one.
    """
    from apps.orders.models import OrderItem

    order_ids = list(
        OrderItem.objects.filter(product=product).values_list(
            "order_id", flat=True
        )
    )
    if not order_ids:
        return []

    co_counts = (
        OrderItem.objects.filter(order_id__in=order_ids)
        .exclude(product=product)
        .exclude(product__isnull=True)
        .values("product")
        .annotate(co_count=Count("order_id"))
        .order_by("-co_count", "-product__sold_count")[:limit]
    )
    ordered_ids = [row["product"] for row in co_counts]
    if not ordered_ids:
        return []

    products = {
        p.pk: p
        for p in Product.objects.active()
        .filter(pk__in=ordered_ids)
        .select_related("category", "brand")
    }
    return [products[pk] for pk in ordered_ids if pk in products]


# --------------------------------------------------------------------------
# Colour variants (management portal)
# --------------------------------------------------------------------------
COLOR_ATTRIBUTE_NAME_EN = "Color"
COLOR_ATTRIBUTE_NAME_AR = "اللون"
_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def get_or_create_color_attribute():
    """Return the shared *Color* attribute, creating it on first use."""
    attribute = (
        Attribute.objects.filter(
            Q(name_en__iexact=COLOR_ATTRIBUTE_NAME_EN)
            | Q(name__iexact=COLOR_ATTRIBUTE_NAME_EN)
            | Q(name_ar__iexact=COLOR_ATTRIBUTE_NAME_AR)
        )
        .order_by("position", "id")
        .first()
    )
    if attribute is None:
        attribute = Attribute(
            name_en=COLOR_ATTRIBUTE_NAME_EN,
            name_ar=COLOR_ATTRIBUTE_NAME_AR,
        )
        attribute.save()
    return attribute


def _normalize_hex(value):
    """Return ``#rrggbb`` for a valid hex string, otherwise ``""``."""
    match = _HEX_RE.match((value or "").strip())
    return f"#{match.group(1).lower()}" if match else ""


def _get_or_create_color_value(attribute, name, color_hex):
    value = (
        AttributeValue.objects.filter(attribute=attribute, value_en__iexact=name)
        .order_by("position", "id")
        .first()
    )
    if value is None:
        value = AttributeValue(attribute=attribute)
    value.value_en = name
    if not value.value_ar:
        value.value_ar = name
    if color_hex:
        value.color_hex = color_hex
    value.save()  # mirrors value_en into the legacy base column
    return value


def _unique_variant_sku(product, color_name, provided=""):
    base = (provided or f"{product.sku}-{slugify(color_name)}").strip()[:64]
    if not base:
        base = f"{product.sku}-VAR"[:64]
    candidate = base
    counter = 2
    while ProductVariant.objects.filter(sku=candidate).exists():
        suffix = f"-{counter}"
        candidate = base[: 64 - len(suffix)] + suffix
        counter += 1
    return candidate


def sync_product_colors(product, rows):
    """Create/update/delete colour variants for ``product``.

    ``rows`` is an iterable of cleaned dictionaries with the keys
    ``variant_id``, ``name``, ``color_hex``, ``stock_quantity``, ``price``,
    ``sku`` and ``delete``. Blank rows (no colour name) are ignored; a row
    flagged for deletion removes its variant.
    """
    color_attribute = get_or_create_color_attribute()
    position = product.variants.aggregate(top=Max("position"))["top"] or 0

    for row in rows:
        variant_id = row.get("variant_id")
        if row.get("delete"):
            if variant_id:
                product.variants.filter(pk=variant_id).delete()
            continue

        name = (row.get("name") or "").strip()
        if not name:
            continue

        value = _get_or_create_color_value(
            color_attribute, name, _normalize_hex(row.get("color_hex"))
        )

        variant = (
            product.variants.filter(pk=variant_id).first() if variant_id else None
        )
        if variant is None:
            position += 1
            variant = ProductVariant(
                product=product,
                sku=_unique_variant_sku(
                    product, name, (row.get("sku") or "").strip()
                ),
                position=position,
            )
        else:
            provided_sku = (row.get("sku") or "").strip()
            if provided_sku and provided_sku != variant.sku:
                variant.sku = _unique_variant_sku(product, name, provided_sku)

        variant.name_en = name
        if not variant.name_ar:
            variant.name_ar = name
        variant.stock_quantity = int(row.get("stock_quantity") or 0)
        variant.price = row.get("price")
        variant.is_active = True
        sync_default_language(variant, "name")
        variant.save()
        variant.attributes.set([value])

    return product