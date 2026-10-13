"""Storefront catalog views: shop, product detail, search."""
import json

from django.contrib import messages
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from apps.core.utils import client_ip, currency, paginate, throttle
from . import services
from .models import AttributeValue, Brand, Category, Product


def _breadcrumbs(*crumbs):
    return [{"title": t, "url": u} for t, u in crumbs if t]


@require_GET
def shop(request):
    qs = services.filter_products(request)
    page_obj = paginate(request, qs)
    context = {
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "sort": request.GET.get("sort", "newest"),
        "current_category": request.GET.get("category", ""),
        "current_brand": request.GET.get("brand", ""),
    }
    context.update(services.shop_context(request))
    context["breadcrumbs"] = _breadcrumbs((_("Shop"), None))
    return render(request, "shop/list.html", context)


@require_GET
def category(request, slug):
    category_obj = get_object_or_404(
        Category.objects.filter(is_active=True), slug=slug
    )
    request.GET = request.GET.copy()
    if "category" not in request.GET:
        request.GET["category"] = slug
    return _category_listing(request, category_obj)


def _category_listing(request, category_obj):
    qs = services.filter_products(request).filter(
        category__in=list(category_obj.all_descendants.values_list("id", flat=True))
    )
    page_obj = paginate(request, qs)
    children = category_obj.get_children()
    context = {
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "category": category_obj,
        "children": children,
        "sort": request.GET.get("sort", "newest"),
        "current_category": request.GET.get("category", category_obj.slug),
        "current_brand": request.GET.get("brand", ""),
        "meta_title": category_obj.seo_title,
        "meta_description": category_obj.seo_description,
        "breadcrumbs": _breadcrumbs(
            (_("Shop"), "/shop/"),
            (category_obj.name, None),
        ),
    }
    context.update(services.shop_context(request))
    return render(request, "shop/category.html", context)


@require_GET
def brand(request, slug):
    brand_obj = get_object_or_404(Brand.objects.filter(is_active=True), slug=slug)
    request.GET = request.GET.copy()
    request.GET["brand"] = slug
    qs = services.filter_products(request).filter(brand=brand_obj)
    page_obj = paginate(request, qs)
    context = {
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "brand": brand_obj,
        "sort": request.GET.get("sort", "newest"),
        "current_brand": slug,
        "meta_title": brand_obj.seo_title or brand_obj.name,
        "meta_description": brand_obj.seo_description,
        "breadcrumbs": _breadcrumbs(
            (_("Shop"), "/shop/"), (_("Brands"), "/brands/"), (brand_obj.name, None)
        ),
    }
    context.update(services.shop_context(request))
    return render(request, "shop/brand.html", context)


@require_GET
def brand_list(request):
    brands = (
        Brand.objects.filter(is_active=True)
        .annotate(
            product_count=Count(
                "products", filter=Q(products__status=Product.Status.ACTIVE)
            )
        )
        .order_by("name")
    )
    return render(request, "shop/brands.html", {
        "brands": brands,
        "breadcrumbs": _breadcrumbs((_("Brands"), None)),
    })


@require_GET
def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category", "brand").filter(
            status=Product.Status.ACTIVE
        ),
        slug=slug,
    )

    Product.objects.filter(pk=product.pk).update(
        view_count=product.view_count + 1
    )
    services.add_to_recently_viewed(request, slug)

    variants = product.variants.filter(is_active=True).prefetch_related(
        "attributes__attribute"
    )
    # Group variant attribute values for size/color pickers.
    option_groups = {}
    for variant in variants:
        for value in variant.attributes.all():
            group = option_groups.setdefault(
                value.attribute_id,
                {"name": value.attribute.name, "values": {}},
            )
            group["values"].setdefault(
                value.pk, {"value": value.value, "hex": value.color_hex}
            )

    reviews = (
        product.reviews.filter(status="approved")
        .select_related("user")
        .prefetch_related("images")
    )
    reviews_page = paginate(request, reviews, per_page=10)

    questions = (
        product.questions.filter(status="approved")
        .select_related("user")
        .prefetch_related("answers__user")
        .order_by("-created_at")
    )
    questions_page = paginate(request, questions, per_page=10)

    rating_breakdown = (
        product.reviews.filter(status="approved")
        .values("rating")
        .annotate(total=Count("id"))
    )
    breakdown = {r["rating"]: r["total"] for r in rating_breakdown}
    total_reviews = sum(breakdown.values()) or 1

    active_variant = None
    if variants:
        active_variant = (
            variants.filter(stock_quantity__gt=0).first() or variants.first()
        )

    context = {
        "product": product,
        "gallery": product.images.all(),
        "variants": variants,
        "option_groups": list(option_groups.values()),
        "active_variant": active_variant,
        "reviews": reviews_page,
        "questions": questions_page,
        "question_count": questions.count(),
        "breakdown": breakdown,
        "total_reviews": product.rating_count,
        "review_avg": product.rating_average,
        "total_reviews_for_avg": total_reviews,
        "related": services.related_products(product),
        "fbt": services.frequently_bought_together(product),
        "breadcrumbs": _breadcrumbs(
            (_("Shop"), "/shop/"),
            (product.category.name, product.category.get_absolute_url()),
            (product.name, None),
        ),
        "structured_data": json.dumps(product.json_ld),
        "meta_title": product.seo_title,
        "meta_description": product.seo_description,
        "meta_keywords": product.meta_keywords,
    }
    return render(request, "products/detail.html", context)


@require_GET
def search(request):
    query = (request.GET.get("q") or "").strip()
    qs = services.filter_products(request)
    if not query:
        qs = Product.objects.none()
    page_obj = paginate(request, qs)
    context = {
        "query": query,
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "result_count": page_obj.paginator.count if query else 0,
        "sort": request.GET.get("sort", "newest"),
        "current_brand": request.GET.get("brand", ""),
        "meta_title": _("Search results for “%(query)s”") % {"query": query} if query else _("Search"),
        "breadcrumbs": _breadcrumbs((_("Search"), None)),
    }
    context.update(services.shop_context(request))
    return render(request, "shop/search.html", context)


@require_GET
def search_suggest(request):
    if not throttle(f"search:{client_ip(request)}", limit=60, period=60):
        return JsonResponse({"results": []}, status=429)
    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})
    products = services.search_products(query, limit=6)
    results = [
        {
            "name": p.name,
            "url": p.get_absolute_url(),
            "image": p.main_image.url if p.main_image else "",
            "price": currency(p.current_price),
            "category": p.category.name,
        }
        for p in products
    ]
    return JsonResponse({"results": results})


@require_POST
def quick_add_to_cart(request):
    """AJAX add-to-cart used by product cards."""
    from apps.cart.services import CartError, add_to_cart

    product = Product.objects.filter(pk=request.POST.get("product")).first()
    if product is None:
        return JsonResponse({"ok": False, "message": _("Product not found.")}, status=404)
    if not request.user.is_authenticated and not request.session.session_key:
        pass  # guest cart is created on demand
    try:
        add_to_cart(request, product, request.POST.get("quantity", 1), None)
    except CartError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    from apps.cart.services import get_cart

    cart = get_cart(request, create=True)
    return JsonResponse({"ok": True, "count": cart.total_quantity})


@require_POST
def stock_alert(request, slug):
    """Subscribe to back-in-stock notifications."""
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError

    product = get_object_or_404(Product, slug=slug, status=Product.Status.ACTIVE)
    variant_id = request.POST.get("variant_id")
    email = (request.POST.get("email") or "").strip().lower()

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"ok": False, "message": _("Please enter a valid email address.")}, status=400)

    variant = None
    if variant_id:
        variant = product.variants.filter(pk=variant_id, is_active=True).first()
        if not variant:
            return JsonResponse({"ok": False, "message": _("Invalid product option.")}, status=400)
    elif product.has_variants:
        # If product has variants but none selected, ask user to pick one
        return JsonResponse({"ok": False, "message": _("Please select a product option first.")}, status=400)

    if variant and variant.is_in_stock:
        return JsonResponse({"ok": False, "message": _("This option is already in stock.")}, status=400)
    if not variant and product.is_in_stock:
        return JsonResponse({"ok": False, "message": _("This product is already in stock.")}, status=400)

    from .models import StockAlert

    alert, created = StockAlert.objects.get_or_create(
        product=product, variant=variant, email=email,
        defaults={"is_active": True},
    )
    if not created and not alert.is_active:
        alert.is_active = True
        alert.notified_at = None
        alert.save(update_fields=["is_active", "notified_at"])
        created = True

    if created:
        return JsonResponse({"ok": True, "message": _("You'll be notified when this item is back in stock.")})
    return JsonResponse({"ok": True, "message": _("You're already subscribed to notifications for this item.")})

