"""Compare products (session-based, guest-friendly)."""
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from . import services
from .services import CartError


def list_view(request):
    """Render the side-by-side comparison table."""
    slugs = services.get_compare_list(request)
    products = []
    if slugs:
        found = Product.objects.filter(
            slug__in=slugs, status=Product.Status.ACTIVE
        ).select_related("brand", "category")
        by_slug = {p.slug: p for p in found}
        products = [by_slug[s] for s in slugs if s in by_slug]
        # Drop slugs for archived/deleted products so the badge stays honest.
        if len(products) != len(slugs):
            request.session["compare"] = [p.slug for p in products]

    best_price_pk = None
    best_rating_pk = None
    if len(products) > 1:
        in_stock = [p for p in products if p.is_in_stock]
        pool = in_stock or products
        best_price_pk = min(pool, key=lambda p: p.current_price).pk
        rated = [p for p in products if p.rating_count]
        if rated:
            best_rating_pk = max(rated, key=lambda p: p.rating_average).pk

    return render(
        request,
        "cart/compare.html",
        {
            "products": products,
            "best_price_pk": best_price_pk,
            "best_rating_pk": best_rating_pk,
        },
    )


@require_POST
def toggle(request):
    """Add/remove a product from the compare list (AJAX)."""
    slug = request.POST.get("slug") or request.POST.get("product")
    product = Product.objects.filter(slug=slug).first()
    if product is None and str(slug).isdigit():
        product = Product.objects.filter(pk=slug).first()
    if product is None:
        return HttpResponseBadRequest(_("Unknown product"))

    try:
        added, count = services.toggle_compare(request, product.slug)
    except CartError as exc:
        return JsonResponse(
            {
                "ok": False,
                "message": str(exc),
                "count": services.get_compare_count(request),
            },
            status=400,
        )
    return JsonResponse({"ok": True, "added": added, "count": count})


@require_POST
def remove(request, slug):
    count = services.remove_from_compare(request, slug)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "count": count})
    return redirect("compare:list")


@require_POST
def clear(request):
    services.clear_compare(request)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "count": 0})
    return redirect("compare:list")
