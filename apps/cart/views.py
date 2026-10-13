"""Shopping cart views."""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.core.utils import client_ip, throttle
from apps.coupons.services import CouponService
from . import services
from .services import CartError, get_cart


def _safe_next(request):
    """Same-origin path to bounce back to: ?next → POST next → referrer → home."""
    for candidate in (
        request.GET.get("next"),
        request.POST.get("next"),
    ):
        if candidate and candidate.startswith("/") and not candidate.startswith("//"):
            return candidate
    referrer = request.META.get("HTTP_REFERER", "")
    path = ""
    if referrer:
        try:
            from urllib.parse import urlparse

            path = urlparse(referrer).path
        except ValueError:
            path = ""
    if path and not path.startswith("//"):
        return path
    return None


def _redirect_target(request, default=None):
    nxt = _safe_next(request)
    if nxt:
        return redirect(nxt)
    if default:
        return redirect(default)
    return redirect("core:home")


def _is_xhr(request):
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _cart_count(request):
    cart = get_cart(request, create=False)
    return cart.total_quantity if cart else 0


@require_POST
def add(request):
    is_xhr = _is_xhr(request)
    product_id = request.POST.get("product")
    quantity = request.POST.get("quantity", 1)
    variant_id = request.POST.get("variant") or request.POST.get("variant_id")

    from apps.catalog.models import Product, ProductVariant

    def fail(message, nxt=None, level="error"):
        if is_xhr:
            return JsonResponse({"ok": False, "message": message})
        getattr(messages, level)(request, message)
        if nxt:
            return redirect(nxt)
        return _redirect_target(request)

    product = Product.objects.filter(pk=product_id).first()
    if product is None:
        return fail(_("That product no longer exists."))

    variant = None
    if variant_id:
        variant = ProductVariant.objects.filter(
            pk=variant_id, product=product
        ).first()
        if variant is None:
            return fail(_("Invalid product option."), nxt="catalog:detail")

    if not throttle(f"cart-add:{client_ip(request)}", limit=60, period=60):
        return fail(_("Too many requests — slow down a little."), level="warning")

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        quantity = 1

    error = None
    try:
        services.add_to_cart(request, product, quantity, variant)
    except CartError as exc:
        error = str(exc)
    else:
        label = product.name + (f" ({variant.name})" if variant else "")
        message = _("Added “%(label)s” to your cart.") % {"label": label}

    if is_xhr:
        if error:
            return JsonResponse({"ok": False, "message": error, "count": _cart_count(request)})
        return JsonResponse({
            "ok": True,
            "count": _cart_count(request),
            "message": message,
            "title": _("Added to cart"),
            "reload": False,
        })

    if error:
        messages.error(request, error)
    else:
        messages.success(request, message)
    return _redirect_target(request)


@require_POST
def update(request):
    is_xhr = _is_xhr(request)
    item_id = request.POST.get("item_id")
    quantity = request.POST.get("quantity", 1)
    error = None
    try:
        services.update_cart_item(request, item_id, quantity)
    except (CartError, ValueError) as exc:
        error = str(exc) if str(exc) else _("Could not update item.")

    if is_xhr:
        if error:
            return JsonResponse({"ok": False, "message": error, "count": _cart_count(request)})
        return JsonResponse({"ok": True, "count": _cart_count(request), "message": _("Cart updated.")})

    if error:
        messages.error(request, error)
    else:
        messages.success(request, _("Cart updated."))
    return _redirect_target(request)


@require_POST
def remove(request):
    is_xhr = _is_xhr(request)
    item_id = request.POST.get("item_id")
    services.remove_cart_item(request, item_id)
    if is_xhr:
        return JsonResponse({"ok": True, "count": _cart_count(request), "message": _("Item removed from cart.")})
    messages.info(request, _("Item removed from cart."))
    return _redirect_target(request)


@require_POST
def apply_coupon(request):
    is_xhr = _is_xhr(request)
    code = (request.POST.get("coupon_code") or "").strip()
    cart = get_cart(request, create=False)
    if cart is None or cart.is_empty:
        if is_xhr:
            return JsonResponse({"ok": False, "message": _("Your cart is empty.")})
        messages.error(request, _("Your cart is empty."))
        return _redirect_target(request)

    user = request.user if request.user.is_authenticated else None
    coupon, error = CouponService.apply_to_cart(cart, code, user=user)
    if error:
        if is_xhr:
            return JsonResponse({"ok": False, "message": error})
        messages.error(request, error)
    else:
        if is_xhr:
            return JsonResponse({
                "ok": True,
                "message": _("Coupon %(code)s applied — %(discount)s.")
                % {"code": coupon.code, "discount": coupon.discount_label},
            })
        messages.success(
            request,
            _("Coupon %(code)s applied — %(discount)s.")
            % {"code": coupon.code, "discount": coupon.discount_label},
        )
    return _redirect_target(request)


@require_POST
def remove_coupon(request):
    is_xhr = _is_xhr(request)
    cart = get_cart(request, create=False)
    if cart:
        CouponService.clear(cart)
        if is_xhr:
            return JsonResponse({"ok": True, "message": _("Coupon removed.")})
        messages.info(request, _("Coupon removed."))
    elif is_xhr:
        return JsonResponse({"ok": True, "message": _("Coupon removed.")})
    return _redirect_target(request)


@never_cache
def mini(request):
    """HTML fragment for the header cart side drawer (fetched on demand)."""
    cart = get_cart(request, create=False)
    totals = services.cart_totals(cart, tax_rate=request_tax_rate())
    return render(request, "includes/mini_cart.html", {
        "cart": cart,
        "totals": totals,
        "coupon": cart.coupon if cart else None,
    })


def request_tax_rate():
    from django.conf import settings

    return settings.TAX_RATE
