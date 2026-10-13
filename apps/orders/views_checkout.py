"""Checkout views: multi-step checkout + order placement."""
import uuid
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.cart.services import get_cart
from apps.core.utils import client_ip, throttle
from apps.coupons.services import CouponService
from .forms import CheckoutForm
from .models import ShippingMethod
from .services import OrderError, create_order, validate_checkout


def _cart_or_redirect(request):
    cart = get_cart(request, create=False)
    if cart is None or cart.is_empty:
        messages.info(request, _("Your cart is empty — add something first."))
        return None
    return cart


@login_required
@require_http_methods(["GET", "POST"])
def start(request):
    """Multi-step checkout page (steps rendered progressively client-side)."""
    cart = _cart_or_redirect(request)
    if cart is None:
        return redirect("catalog:shop")

    if request.method == "POST":
        return place(request)

    if request.GET.get("quote"):
        return _quote(request, cart)

    user = request.user if request.user.is_authenticated else None
    initial = {}
    saved_address = None
    if user:
        saved_address = user.addresses.filter(
            is_default=True, address_type="shipping"
        ).first() or user.addresses.filter(address_type="shipping").first()
        if saved_address:
            initial = {
                "full_name": saved_address.full_name,
                "phone": saved_address.phone or user.phone,
                "address_line1": saved_address.address_line1,
                "address_line2": saved_address.address_line2,
                "city": saved_address.city,
                "state": saved_address.state,
                "country": saved_address.country,
                "postal_code": saved_address.postal_code,
            }

    # Generate idempotency key for this checkout session
    idempotency_key = request.session.get("checkout_idempotency_key")
    if not idempotency_key:
        idempotency_key = uuid.uuid4().hex
        request.session["checkout_idempotency_key"] = idempotency_key

    form = CheckoutForm(user=user, initial=initial)
    context = _checkout_context(request, cart, form)
    context["idempotency_key"] = idempotency_key
    return render(request, "checkout/checkout.html", context)


def _quote(request, cart):
    """Live totals for the sticky summary (JSON; prices always recomputed)."""
    from django.http import JsonResponse

    from apps.cart.services import cart_totals
    from apps.core.utils import currency

    method = ShippingMethod.objects.filter(
        code=request.GET.get("method", ""), is_active=True
    ).first()
    totals = cart_totals(cart, shipping_method=method)
    return JsonResponse({
        "shipping": currency(totals["shipping"]),
        "discount": currency(totals["discount"]),
        "tax": currency(totals["tax"]),
        "total": currency(totals["total"]),
    })


def _checkout_context(request, cart, form):
    from apps.core.utils import money

    methods = ShippingMethod.objects.filter(is_active=True).order_by("position")
    coupon = cart.coupon
    totals_preview = {
        "subtotal": cart.subtotal,
        "discount": money(0),
        "shipping": money(0),
        "tax": money(0),
        "total": cart.subtotal,
    }
    if coupon:
        try:
            coupon.validate(
                user=request.user if request.user.is_authenticated else None,
                subtotal=cart.subtotal,
            )
            totals_preview["discount"] = coupon.compute_discount(
                cart.subtotal
            )
        except Exception:
            CouponService.clear(cart)
            coupon = None
    return {
        "cart": cart,
        "form": form,
        "totals": totals_preview,
        "coupon": coupon,
        "shipping_methods": methods,
        "saved_addresses": request.user.addresses.all()
        if request.user.is_authenticated else [],
    }


@login_required
@require_POST
def place(request):
    """Validate everything server-side, then create the order."""
    if not throttle(f"checkout:{client_ip(request)}", limit=15, period=300):
        messages.error(request, _("Too many checkout attempts. Please wait."))
        return redirect("checkout:start")

    # Validate idempotency key matches session
    # Accept from POST data (form) or fall back to session for backward compatibility
    submitted_key = request.POST.get("idempotency_key", "") or request.session.get("checkout_idempotency_key", "")
    session_key = request.session.get("checkout_idempotency_key", "")
    if submitted_key != session_key:
        messages.error(request, _("Invalid checkout session. Please try again."))
        return redirect("checkout:start")

    user = request.user
    form = CheckoutForm(request.POST, user=user)

    # Store email in session for abandoned cart recovery (even if validation fails)
    email = request.POST.get("email", "").strip().lower()
    if email:
        request.session["checkout_email"] = email

    if not form.is_valid():
        messages.error(
            request, _("Please correct the highlighted fields and try again.")
        )
        return render(
            request,
            "checkout/checkout.html",
            _checkout_context(request, get_cart(request, create=False), form),
            status=400,
        )

    try:
        data = validate_checkout(request, form)
        order = create_order(request, data, idempotency_key=submitted_key)
    except OrderError as exc:
        messages.error(request, str(exc))
        return render(
            request,
            "checkout/checkout.html",
            _checkout_context(request, get_cart(request, create=False), form),
            status=400,
        )

    # Remember the order so guests can open the payment / confirmation pages.
    request.session["last_order"] = order.order_number

    # Provider-specific redirect (COD goes straight to confirmation).
    from apps.payments.gateways import get_gateway

    gateway = get_gateway(order.payment_method)
    try:
        provider_data = gateway.create_payment(order, request=request)
    except Exception as exc:  # pragma: no cover - provider outage
        messages.warning(
            request,
            _("Order %(order)s was created, but the payment step needs attention: %(error)s")
            % {"order": order.order_number, "error": exc},
        )
        return redirect("orders:detail", order_number=order.order_number)

    if provider_data.get("requires_action"):
        if order.payment_method == "paypal" and provider_data.get("approve_url"):
            from django.http import HttpResponseRedirect

            return HttpResponseRedirect(provider_data["approve_url"])
        if order.payment_method == "stripe":
            return redirect(
                "payments:stripe_pay", order_number=order.order_number
            )

    messages.success(
        request,
        _("Order %(order)s placed successfully! Confirmation sent to %(email)s.")
        % {"order": order.order_number, "email": order.email},
    )
    return redirect("orders:detail", order_number=order.order_number)
