"""Cart context: header badges for cart, wishlist and compare."""
from apps.cart.services import get_cart, get_compare_list, get_wishlist_count


def cart_context(request):
    """Expose cart/wishlist/compare counters for the storefront header."""
    context = {
        "cart_count": 0,
        "wishlist_count": 0,
        "compare_count": 0,
        "compare_slugs": [],
    }
    user = getattr(request, "user", None)
    try:
        # Cart works for guests too (session cart) — badge must always show.
        cart = get_cart(request, create=False)
        context["cart_count"] = cart.total_quantity if cart else 0
        # Compare is session-based, so it works for guests too.
        compare = get_compare_list(request)
        context["compare_count"] = len(compare)
        context["compare_slugs"] = compare
        if user is not None and user.is_authenticated:
            context["wishlist_count"] = get_wishlist_count(user)
    except Exception:  # pragma: no cover - never break page rendering
        pass
    return context
