"""Storefront and error views for the core app."""
from django.shortcuts import render


def home(request):
    """Render the storefront homepage with real data from the database."""
    from django.db.models import Avg, Count, Prefetch, Q

    from apps.catalog.models import Category, Product
    from apps.coupons.models import Coupon

    featured = (
        Product.objects.active()
        .select_related("category", "brand")
        .filter(is_featured=True)[:8]
    )
    new_arrivals = (
        Product.objects.active()
        .select_related("category", "brand")
        .filter(is_new_arrival=True)[:8]
    )
    best_sellers = (
        Product.objects.active()
        .select_related("category", "brand")
        .filter(is_best_seller=True)
        .order_by("-sold_count")[:8]
    )
    on_sale = (
        Product.objects.active()
        .select_related("category", "brand")
        .on_sale()
        .order_by("-created_at")[:8]
    )
    children = Category.objects.filter(is_active=True).order_by("position", "name")
    categories = (
        Category.objects.filter(is_active=True, parent__isnull=True)
        .annotate(
            product_count=Count(
                "products", filter=Q(products__status=Product.Status.ACTIVE)
            )
        )
        .prefetch_related(Prefetch("children", queryset=children))
        .order_by("position", "name")[:8]
    )

    # Testimonials: latest approved reviews with a rating of 4+
    from apps.reviews.models import Review

    testimonials = (
        Review.objects.filter(status=Review.Status.APPROVED, rating__gte=4)
        .select_related("user", "product")
        .order_by("-created_at")[:6]
    )

    from django.utils import timezone

    active_coupon = (
        Coupon.objects.filter(is_active=True, valid_from__lte=timezone.now())
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=timezone.now()))
        .order_by("-created_at")
        .first()
    )

    context = {
        "featured_products": featured,
        "new_arrivals": new_arrivals,
        "best_sellers": best_sellers,
        "on_sale_products": on_sale,
        "categories": categories,
        "testimonials": testimonials,
        "active_coupon": active_coupon,
        "total_products": Product.objects.active().count(),
        "total_categories": Category.objects.filter(is_active=True).count(),
        "avg_rating": (
            Product.objects.active().aggregate(a=Avg("rating_average"))["a"] or 0
        ),
    }
    return render(request, "home/index.html", context)


def robots(request):
    """Serve robots.txt."""
    from django.http import HttpResponse

    return HttpResponse(
        "User-agent: *\nAllow: /\nDisallow: /management/\n"
        f"Sitemap: {request.build_absolute_uri('/sitemap.xml')}\n",
        content_type="text/plain",
    )


# --------------------------------------------------------------------------
# Error handlers
# --------------------------------------------------------------------------
def bad_request(request, exception=None):
    return render(request, "errors/400.html", status=400)


def permission_denied(request, exception=None):
    return render(request, "errors/403.html", status=403)


def page_not_found(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error(request):
    return render(request, "errors/500.html", status=500)

