"""Wishlist views."""
from django.contrib import messages
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from . import services
from .services import CartError


def _is_xhr(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _back_to_page(request):
    """Bounce back to where the user was (never to the removed wishlist page)."""
    from .views import _safe_next

    nxt = _safe_next(request)
    if nxt:
        return redirect(nxt)
    return redirect("core:home")


@never_cache
def mini(request):
    """HTML fragment for the header wishlist side drawer."""
    items = []
    if request.user.is_authenticated:
        items = services.wishlist_items(request.user)
    return render(request, "includes/mini_wishlist.html", {
        "items": items,
        "wishlist_count": services.get_wishlist_count(request.user),
    })


@require_POST
def toggle(request):
    if not request.user.is_authenticated:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"authenticated": False}, status=401)
        return redirect(f"/login/?next={request.get_full_path()}")

    slug = request.POST.get("slug") or request.POST.get("product")
    product = Product.objects.filter(slug=slug).first() or Product.objects.filter(
        pk=slug
    ).first()
    if product is None:
        return HttpResponseBadRequest(_("Unknown product"))

    try:
        wished, count = services.toggle_wishlist(request.user, product)
    except CartError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)

    return JsonResponse({
        "ok": True,
        "wished": wished,
        "count": count,
        "authenticated": True,
    })


@require_POST
def remove(request, pk):
    if not request.user.is_authenticated:
        if _is_xhr(request):
            return JsonResponse({"authenticated": False}, status=401)
        return redirect("accounts:login")
    from .models import WishlistItem

    WishlistItem.objects.filter(pk=pk, user=request.user).delete()
    if _is_xhr(request):
        return JsonResponse({
            "ok": True,
            "count": services.get_wishlist_count(request.user),
            "message": _("Removed from wishlist."),
        })
    messages.info(request, _("Removed from wishlist."))
    return _back_to_page(request)


@require_POST
def move_to_cart(request, pk):
    if not request.user.is_authenticated:
        if _is_xhr(request):
            return JsonResponse({"authenticated": False}, status=401)
        return redirect("accounts:login")
    from .models import WishlistItem

    item = WishlistItem.objects.filter(pk=pk, user=request.user).select_related(
        "product"
    ).first()
    if item is None:
        if _is_xhr(request):
            return JsonResponse({"ok": False, "message": _("Wishlist item not found.")}, status=404)
        messages.error(request, _("Wishlist item not found."))
        return _back_to_page(request)
    try:
        services.add_to_cart(request, item.product, 1, None)
    except CartError as exc:
        if _is_xhr(request):
            return JsonResponse({"ok": False, "message": str(exc)}, status=400)
        messages.error(request, str(exc))
        return _back_to_page(request)
    item.delete()
    name = item.product.name
    if _is_xhr(request):
        cart = services.get_cart(request, create=False)
        return JsonResponse({
            "ok": True,
            "count": services.get_wishlist_count(request.user),
            "cart_count": cart.total_quantity if cart else 0,
            "message": _("“%(name)s” moved to your cart.") % {"name": name},
        })
    messages.success(request, _("“%(name)s” moved to your cart.") % {"name": name})
    return _back_to_page(request)
