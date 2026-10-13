"""Payment views: Stripe page + webhook, PayPal return/cancel."""
import json
import logging

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.orders.models import Order
from apps.orders.services import transition_status
from .gateways import GatewayError, get_gateway
from .models import Payment

logger = logging.getLogger(__name__)


def _own_order(request, order_number):
    """The order's owner, or a guest holding the order in their session."""
    order = get_object_or_404(Order, order_number=order_number)
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        # Guest checkout: the session that placed the order may pay it.
        if request.session.get("last_order") == order.order_number:
            return order
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied(_("You cannot access this payment."))
    if order.user_id != user.pk and not user.is_management:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied(_("You cannot access this payment."))
    return order


@require_GET
def stripe_pay(request, order_number):
    """Card entry page (Stripe.js / Elements) — only when Stripe is configured."""
    from django.conf import settings

    if not settings.STRIPE_SECRET_KEY:
        messages.error(request, _("Card payments are not configured yet."))
        return redirect("orders:detail", order_number=order_number)

    order = _own_order(request, order_number)
    gateway = get_gateway("stripe")
    try:
        data = gateway.create_payment(order, request=request)
    except GatewayError as exc:
        messages.error(request, str(exc))
        return redirect("orders:detail", order_number=order_number)

    return render(request, "checkout/stripe_pay.html", {
        "order": order,
        "client_secret": data.get("client_secret", ""),
        "stripe_public_key": settings.STRIPE_PUBLIC_KEY,
    })


@require_POST
def stripe_confirm(request, order_number):
    """Server-side verification of a PaymentIntent (never trusts the client)."""
    order = _own_order(request, order_number)
    payload = json.loads(request.body or "{}")
    gateway = get_gateway("stripe")
    try:
        result = gateway.confirm_payment(order, payload)
    except GatewayError as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)

    if result.get("status") == "paid":
        _mark_paid(order, "stripe", payload)
        return JsonResponse({
            "ok": True,
            "redirect": _after_payment_url(request, order),
        })
    return JsonResponse({
        "ok": False,
        "message": _("Payment status: %(status)s") % {"status": result.get("status")},
    }, status=400)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Stripe webhook — signature verified before any state change."""
    import stripe

    from django.conf import settings

    if not settings.STRIPE_WEBHOOK_SECRET:
        return HttpResponse(status=400)
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    obj = event.get("object", {})
    order_number = (obj.get("metadata") or {}).get("order_number")
    if event["type"] == "payment_intent.succeeded" and order_number:
        order = Order.objects.filter(order_number=order_number).first()
        if order:
            _mark_paid(order, "stripe", {"payment_intent": obj.get("id")})
    elif event["type"] == "payment_intent.payment_failed" and order_number:
        order = Order.objects.filter(order_number=order_number).first()
        if order:
            Payment.objects.filter(order=order, provider="stripe").update(
                status=Payment.Status.FAILED,
                error_message=_("Payment failed"),
            )
            order.payment_status = "failed"
            order.save(update_fields=["payment_status"])
            _notify(order, _("Payment failed"), _("Your card payment was declined."))
    return HttpResponse(status=200)


def _after_payment_url(request, order):
    """Guests land on the (session-verified) tracking page, not the 403 detail."""
    if getattr(request, "user", None) and request.user.is_authenticated:
        return f"/orders/{order.order_number}/"
    request.session[f"track_verified_{order.order_number}"] = True
    return f"/orders/track/{order.order_number}/"


def _mark_paid(order, provider, payload=None):
    payment = Payment.objects.filter(order=order, provider=provider).first()
    if payment and payment.status != Payment.Status.PAID:
        payment.status = Payment.Status.PAID
        payment.paid_at = timezone.now()
        payment.webhook_received = True
        payment.save()
    if order.is_paid:
        return
    order.payment_status = "paid"
    order.save(update_fields=["payment_status"])

    from apps.notifications.email import send_order_email

    send_order_email(order, "paid")
    _notify(order, _("Payment received"),
            _("We received your payment of %(total)s.") % {"total": order.total})
    if order.status == Order.Status.PENDING:
        try:
            transition_status(order, Order.Status.CONFIRMED, note=_("Payment received"))
        except Exception:  # pragma: no cover
            logger.exception("Could not confirm order %s", order.order_number)


def _notify(order, title, body):
    if order.user_id is None:
        return
    from apps.notifications.models import Notification

    Notification.objects.create(
        user=order.user,
        type=Notification.Type.PAYMENT,
        title=title,
        body=body,
        link=f"/orders/{order.order_number}/",
    )


# --------------------------------------------------------------------------
# PayPal
# --------------------------------------------------------------------------
@require_GET
def paypal_return(request, order_number):
    order = _own_order(request, order_number)
    gateway = get_gateway("paypal")
    try:
        result = gateway.confirm_payment(order)
    except GatewayError as exc:
        messages.error(request, str(exc))
        return redirect("orders:detail", order_number=order_number)
    if result.get("status") == "paid":
        _mark_paid(order, "paypal")
        messages.success(request, _("PayPal payment completed — thank you!"))
    else:
        messages.warning(
            request,
            _("PayPal payment is “%(status)s”. We will update you once it settles.")
            % {"status": result.get("status")},
        )
    return redirect(_after_payment_url(request, order))


@require_GET
def paypal_cancel(request, order_number):
    messages.info(
        request, _("PayPal payment cancelled — you can retry from your order.")
    )
    return redirect("orders:detail", order_number=order_number)

