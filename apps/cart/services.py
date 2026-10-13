"""Cart and wishlist service layer (all business logic in one place)."""
from decimal import Decimal

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.utils import money
from apps.coupons.services import CouponService
from .models import Cart, CartItem, WishlistItem


class CartError(Exception):
    """Raised when a cart operation is invalid (message is user-facing)."""


def _session_key(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def get_cart(request, create=False):
    """Return the cart for the current user or anonymous session."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        cart = Cart.objects.filter(user=user).first()
        if cart is None and create:
            cart = Cart.objects.create(user=user)
        return cart

    key = request.session.session_key or ""
    cart = Cart.objects.filter(session_key=key).first() if key else None
    if cart is None and create:
        cart = Cart.objects.create(session_key=_session_key(request))
    return cart


def _validate_coupon(cart):
    """Re-validate the cart's coupon against current items.

    If coupon is no longer applicable (e.g., scope-limited, expired, or
    minimum order not met), remove it from the cart.
    """
    if not cart or not cart.coupon_code:
        return

    user = cart.user
    subtotal = cart.subtotal

    coupon, error = CouponService.lookup(cart.coupon_code, user=user, subtotal=subtotal)
    if error:
        cart.coupon_code = ""
        cart.save(update_fields=["coupon_code", "updated_at"])
        return

    # Scope check: for product/category-scoped coupons, ensure at least
    # one eligible item remains in the cart
    if coupon.scope != coupon.Scope.ALL:
        eligible = CouponService.eligible_subtotal(cart, coupon)
        if eligible <= 0:
            cart.coupon_code = ""
            cart.save(update_fields=["coupon_code", "updated_at"])


def get_wishlist_count(user):
    if user is None or not user.is_authenticated:
        return 0
    return WishlistItem.objects.filter(user=user).count()


def merge_guest_cart(request, user):
    """Move an anonymous cart onto a freshly authenticated user's cart."""
    key = request.session.session_key
    if not key:
        return None
    guest_cart = Cart.objects.filter(session_key=key, user__isnull=True).first()
    if guest_cart is None:
        return None

    user_cart, _ = Cart.objects.get_or_create(user=user)
    for item in guest_cart.items.all():
        existing = CartItem.objects.filter(
            cart=user_cart, product=item.product, variant=item.variant
        ).first()
        if existing:
            existing.quantity += item.quantity
            existing.save(update_fields=["quantity"])
        else:
            item.cart = user_cart
            item.save(update_fields=["cart"])
    if guest_cart.coupon_code and not user_cart.coupon_code:
        user_cart.coupon_code = guest_cart.coupon_code
        user_cart.save(update_fields=["coupon_code"])
    guest_cart.delete()
    request.session.pop("cart", None)
    return user_cart


def add_to_cart(request, product, quantity=1, variant=None):
    """Add a product/variant to the cart with stock validation."""
    quantity = max(int(quantity or 1), 1)

    if product.status != product.Status.ACTIVE:
        raise CartError(_("This product is not available."))

    if variant is not None and variant.product_id != product.pk:
        raise CartError(_("That option does not belong to this product."))

    target = variant if variant else product
    available = target.available_quantity
    if available <= 0:
        raise CartError(_("Sorry, this item is out of stock."))

    cart = get_cart(request, create=True)
    with transaction.atomic():
        item, created = CartItem.objects.get_or_create(
            cart=cart, product=product, variant=variant,
            defaults={"quantity": 0},
        )
        desired = item.quantity + quantity
        if desired > available:
            if item.quantity == 0:
                item.quantity = available
            else:
                raise CartError(
                    _("Only %(count)s left in stock for %(product)s.")
                    % {"count": available, "product": product.name}
                )
        else:
            item.quantity = desired
        item.save(update_fields=["quantity"])
    _validate_coupon(cart)
    return cart


def update_cart_item(request, item_id, quantity):
    """Update quantity, clamping to available stock."""
    cart = get_cart(request, create=False)
    if cart is None:
        raise CartError(_("Your cart is empty."))
    item = CartItem.objects.filter(pk=item_id, cart=cart).select_related(
        "product", "variant"
    ).first()
    if item is None:
        raise CartError(_("Cart item not found."))

    quantity = int(quantity)
    if quantity <= 0:
        item.delete()
        _validate_coupon(cart)
        return cart
    target = item.variant if item.variant else item.product
    available = target.available_quantity
    if quantity > available:
        raise CartError(_("Only %(count)s in stock.") % {"count": available})
    item.quantity = quantity
    item.save(update_fields=["quantity"])
    _validate_coupon(cart)
    return cart


def remove_cart_item(request, item_id):
    cart = get_cart(request, create=False)
    if cart:
        CartItem.objects.filter(pk=item_id, cart=cart).delete()
        _validate_coupon(cart)
    return cart


def cart_totals(cart, coupon=None, shipping_method=None, tax_rate=Decimal("0")):
    """Compute cart totals server-side. Prices always come from the DB."""
    items = list(cart.items.select_related("product", "variant")) if cart else []
    subtotal = money(sum(i.line_total for i in items))
    base_subtotal = money(sum(i.line_base_total for i in items))
    total_weight = cart.total_weight if cart else Decimal("0")

    discount = money(0)
    coupon_obj = coupon if coupon is not None else (cart.coupon if cart else None)
    if coupon_obj is not None:
        discount = coupon_obj.compute_discount(
            subtotal, shipping=shipping_method.price_for(subtotal, weight=total_weight)
            if shipping_method else Decimal("0.00")
        )
        discount = min(discount, subtotal)

    discounted = money(max(subtotal - discount, Decimal("0.00")))
    tax = money(discounted * Decimal(str(tax_rate)))
    shipping = (
        shipping_method.price_for(discounted, weight=total_weight) if shipping_method else money(0)
    )
    if coupon_obj is not None and coupon_obj.type == coupon_obj.Type.FREE_SHIPPING:
        shipping = money(0)
    total = money(discounted + tax + shipping)
    return {
        "items": items,
        "subtotal": subtotal,
        "base_subtotal": base_subtotal,
        "savings": money(max(base_subtotal - subtotal, Decimal("0.00"))),
        "discount": discount,
        "discounted_subtotal": discounted,
        "tax": tax,
        "tax_rate": tax_rate,
        "shipping": shipping,
        "total": total,
        "total_weight": total_weight,
    }


# --------------------------------------------------------------------------
# Wishlist
# --------------------------------------------------------------------------
def toggle_wishlist(user, product):
    """Toggle a product on the user's wishlist. Returns (wished, count)."""
    if user is None or not user.is_authenticated:
        raise CartError(_("Sign in to use your wishlist."))
    existing = WishlistItem.objects.filter(user=user, product=product).first()
    if existing:
        existing.delete()
        wished = False
    else:
        WishlistItem.objects.create(user=user, product=product)
        wished = True
    return wished, get_wishlist_count(user)


def wishlist_items(user):
    return (
        WishlistItem.objects.filter(user=user)
        .select_related("product", "product__brand", "product__category")
        .order_by("-created_at")
    )


# --------------------------------------------------------------------------
# Compare (session-based — works for guests, no account needed)
# --------------------------------------------------------------------------
COMPARE_MAX = 4


def get_compare_list(request):
    """Return the compare list (ordered slugs) stored in the session."""
    slugs = request.session.get("compare", [])
    if not isinstance(slugs, list):
        return []
    return [s for s in slugs if isinstance(s, str)]


def get_compare_count(request):
    return len(get_compare_list(request))


def toggle_compare(request, slug):
    """Toggle a product on the compare list. Returns (added, count)."""
    slugs = get_compare_list(request)
    if slug in slugs:
        slugs.remove(slug)
        added = False
    else:
        if len(slugs) >= COMPARE_MAX:
            raise CartError(
                _(
                    "You can compare up to %(count)s products. "
                    "Remove one to add another."
                )
                % {"count": COMPARE_MAX}
            )
        slugs.append(slug)
        added = True
    request.session["compare"] = slugs
    return added, len(slugs)


def remove_from_compare(request, slug):
    slugs = get_compare_list(request)
    if slug in slugs:
        slugs.remove(slug)
        request.session["compare"] = slugs
    return len(slugs)


def clear_compare(request):
    request.session["compare"] = []
    return 0