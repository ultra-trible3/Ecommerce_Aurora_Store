"""Order creation service — server-side pricing, stock and validation.

Nothing sent by the browser is trusted: prices, discounts, tax and shipping
are all recomputed from the database inside a single transaction.
"""
import logging
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.cart.models import Cart
from apps.cart.services import cart_totals
from apps.core.utils import generate_order_number, money
from apps.coupons.models import Coupon
from apps.coupons.services import CouponService
from apps.inventory.services import reserve_stock, release_stock
from apps.notifications.models import Notification
from .models import CouponRedemption, Order, OrderItem, OrderStatusHistory, ShippingMethod

logger = logging.getLogger(__name__)


class OrderError(Exception):
    """User-facing checkout error."""


class CheckoutData:
    """Validated checkout payload."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def validate_checkout(request, form):
    """Validate the checkout formset and build a CheckoutData object.

    Raises ``OrderError`` with a user-facing message when invalid.
    """
    user = request.user if request.user.is_authenticated else None

    cart = Cart.objects.filter(user=user).first() if user else None
    if cart is None:
        key = request.session.session_key
        cart = Cart.objects.filter(session_key=key).first() if key else None
    if cart is None or cart.is_empty:
        raise OrderError(_("Your cart is empty."))
    if cart.has_out_of_stock_items:
        raise OrderError(
            _(
                "Some items in your cart are out of stock. "
                "Please adjust your cart and try again."
            )
        )

    method_code = form.cleaned_data.get("shipping_method") or ""
    shipping_method = ShippingMethod.objects.filter(
        code=method_code, is_active=True
    ).first()
    if shipping_method is None:
        raise OrderError(_("Please choose a valid shipping method."))
    
    # Check if shipping method is available for the shipping address
    shipping_country = form.cleaned_data.get("country", _("United States"))
    shipping_state = form.cleaned_data.get("state", "")
    shipping_postal = form.cleaned_data.get("postal_code", "")
    if not shipping_method.is_available_for(shipping_country, shipping_state, shipping_postal):
        raise OrderError(
            _(
                "The selected shipping method is not available for your address "
                "(%(country)s). Please choose another method."
            )
            % {"country": shipping_country}
        )

    payment_method = form.cleaned_data.get("payment_method") or "cod"
    from apps.payments.gateways import available_gateways

    if payment_method not in ("cod", "stripe", "paypal"):
        raise OrderError(_("Invalid payment method."))
    if payment_method not in available_gateways():
        raise OrderError(
            _(
                "That payment method is not available right now. "
                "Please choose another one."
            )
        )

    # Coupon validation (expiration, limits, scope) — server side.
    coupon = None
    coupon_code = (form.cleaned_data.get("coupon_code") or cart.coupon_code or "").strip()
    if coupon_code:
        totals_preview = cart_totals(
            cart, coupon=None, shipping_method=shipping_method,
            tax_rate=_tax_rate(),
        )
        coupon, error = CouponService.lookup(
            coupon_code, user=user, subtotal=totals_preview["subtotal"]
        )
        if error:
            raise OrderError(_("Coupon error: %(error)s") % {"error": error})
        if coupon.scope != Coupon.Scope.ALL:
            eligible = CouponService.eligible_subtotal(cart, coupon)
            if eligible <= 0:
                raise OrderError(
                    _("This coupon does not apply to the items in your cart.")
                )

    return CheckoutData(
        cart=cart,
        user=user,
        shipping_method=shipping_method,
        payment_method=payment_method,
        coupon=coupon,
        form=form,
    )


def _tax_rate():
    from django.conf import settings

    return Decimal(str(settings.TAX_RATE))


def compute_order_totals(data):
    """Recompute every order total from the database (never from the client)."""
    totals = cart_totals(
        data.cart,
        coupon=data.coupon,
        shipping_method=data.shipping_method,
        tax_rate=_tax_rate(),
    )
    return totals


@transaction.atomic
def create_order(request, data, idempotency_key=None):
    """Create an order from validated checkout data.

    Performs: price snapshot, inventory reservation, coupon redemption,
    payment record, notifications and cart cleanup — all atomically.
    
    If `idempotency_key` is provided, checks for an existing order with
    that key and returns it instead of creating a duplicate.
    """
    # Check for existing order with this idempotency key
    if idempotency_key:
        existing_order_number = cache.get(f"idempotency:{idempotency_key}")
        if existing_order_number:
            # Return the already-created order
            return Order.objects.get(order_number=existing_order_number)

    totals = compute_order_totals(data)
    if not totals["items"]:
        raise OrderError(_("Your cart is empty."))

    # Lock product rows to prevent concurrent oversell.
    product_ids = sorted({i.product_id for i in totals["items"]})
    variant_ids = sorted({i.variant_id for i in totals["items"] if i.variant_id})
    from apps.catalog.models import Product, ProductVariant

    products = {
        p.pk: p
        for p in Product.objects.select_for_update().filter(pk__in=product_ids)
    }
    variants = {
        v.pk: v
        for v in ProductVariant.objects.select_for_update().filter(pk__in=variant_ids)
    }

    # Re-validate stock under the lock.
    for item in totals["items"]:
        target = variants.get(item.variant_id) if item.variant_id else products.get(
            item.product_id
        )
        if target is None:
            raise OrderError(_("A product in your cart is no longer available."))
        if target.available_quantity < item.quantity:
            raise OrderError(
                _(
                    "Not enough stock for “%(product)s” "
                    "(only %(count)s left)."
                )
                % {"product": item.product.name, "count": target.available_quantity}
            )

    form = data.form
    shipping = form.cleaned_data
    order = Order(
        order_number=generate_order_number(),
        user=data.user,
        email=shipping["email"],
        guest_name=shipping.get("full_name") or "",
        guest_phone=shipping.get("phone") or "",
        shipping_full_name=shipping["full_name"],
        shipping_phone=shipping["phone"],
        shipping_address_line1=shipping["address_line1"],
        shipping_address_line2=shipping.get("address_line2", ""),
        shipping_city=shipping["city"],
        shipping_state=shipping.get("state", ""),
        shipping_country=shipping.get("country", _("United States")),
        shipping_postal_code=shipping["postal_code"],
        billing_full_name=shipping.get("billing_full_name", ""),
        billing_phone=shipping.get("billing_phone", ""),
        billing_address_line1=shipping.get("billing_address_line1", ""),
        billing_address_line2=shipping.get("billing_address_line2", ""),
        billing_city=shipping.get("billing_city", ""),
        billing_state=shipping.get("billing_state", ""),
        billing_country=shipping.get("billing_country", ""),
        billing_postal_code=shipping.get("billing_postal_code", ""),
        same_as_shipping=shipping.get("same_as_shipping", True),
        shipping_method_name=data.shipping_method.name,
        shipping_method_code=data.shipping_method.code,
        shipping_method_price=totals["shipping"],
        payment_method=data.payment_method,
        subtotal=totals["subtotal"],
        discount=totals["discount"],
        tax=totals["tax"],
        shipping_cost=totals["shipping"],
        total=totals["total"],
        coupon=data.coupon,
        coupon_code=data.coupon.code if data.coupon else "",
        notes=shipping.get("notes", ""),
        status=Order.Status.PENDING,
        payment_status="pending",
    )
    order.save()

    # Historical line-item snapshots.
    order_items = []
    for item in totals["items"]:
        product = products[item.product_id]
        order_items.append(OrderItem(
            order=order,
            product=product,
            variant=item.variant,
            product_name=product.name,
            product_slug=product.slug,
            product_sku=(item.variant.sku if item.variant else product.sku),
            variant_name=item.variant.name if item.variant else "",
            image_url=item.image_url,
            unit_price=item.unit_price,
            original_price=item.base_unit_price,
            quantity=item.quantity,
            line_total=item.line_total,
        ))
    OrderItem.objects.bulk_create(order_items)

    # Inventory: reserve stock and write the ledger.
    for item in order_items:
        reserve_stock(
            product_id=item.product_id,
            variant_id=item.variant_id,
            quantity=item.quantity,
            reference=order.order_number,
            transaction_type="sale",
        )

    # Coupon redemption bookkeeping.
    if data.coupon:
        CouponRedemption.objects.create(
            coupon=data.coupon,
            order=order,
            user=data.user,
            discount_amount=totals["discount"],
        )
        Coupon.objects.filter(pk=data.coupon.pk).update(
            used_count=models_f_used_count(data.coupon)
        )

    # Status history baseline.
    OrderStatusHistory.objects.create(
        order=order,
        from_status="",
        to_status=Order.Status.PENDING,
        note=_("Order placed"),
        actor=data.user,
    )

    # Payment record (provider confirmation happens in payments app).
    from apps.payments.models import Payment

    Payment.objects.create(
        order=order,
        provider=data.payment_method,
        status=Payment.Status.PENDING,
        amount=order.total,
    )

    # Notifications + email.
    _notify_customer(order)
    _notify_admins(order)
    _send_emails(order)

    # Clear the cart.
    data.cart.clear()
    
    # Store idempotency key after successful order creation
    if idempotency_key:
        cache.set(f"idempotency:{idempotency_key}", order.order_number, timeout=86400)  # 24hr
        # Clear from session
        if hasattr(request, 'session'):
            request.session.pop("checkout_idempotency_key", None)

    return order


def models_f_used_count(coupon):
    from django.db.models import F

    return F("used_count") + 1


def _notify_customer(order):
    if order.user is None:
        return
    ct = ContentType.objects.get_for_model(Order)
    Notification.objects.create(
        user=order.user,
        type=Notification.Type.ORDER,
        title=_("Order %(number)s placed") % {"number": order.order_number},
        body=_("We received your order totalling %(total)s.") % {"total": order.total},
        link=f"/orders/{order.order_number}/",
        content_type=ct,
        object_id=order.pk,
    )


def _notify_admins(order):
    from django.contrib.auth import get_user_model

    from apps.notifications.models import Setting

    User = get_user_model()
    recipients = User.objects.filter(
        role__in=[User.Role.ADMIN, User.Role.STAFF], is_active=True
    )
    ct = ContentType.objects.get_for_model(Order)
    for admin in recipients:
        Notification.objects.create(
            user=admin,
            type=Notification.Type.SYSTEM,
            title=_("New order %(number)s") % {"number": order.order_number},
            body=_("%(customer)s · %(total)s · %(count)s item(s)")
            % {
                "customer": order.customer_name,
                "total": order.total,
                "count": order.items.count(),
            },
            link=f"/management/orders/{order.order_number}/",
            content_type=ct,
            object_id=order.pk,
        )


def _send_emails(order):
    from apps.notifications.email import send_order_email

    send_order_email(order, "confirmation")


# --------------------------------------------------------------------------
# Order state transitions
# --------------------------------------------------------------------------
ALLOWED_TRANSITIONS = {
    Order.Status.PENDING: [Order.Status.CONFIRMED, Order.Status.CANCELLED],
    Order.Status.CONFIRMED: [Order.Status.PROCESSING, Order.Status.CANCELLED],
    Order.Status.PROCESSING: [Order.Status.PACKED, Order.Status.CANCELLED],
    Order.Status.PACKED: [Order.Status.SHIPPED],
    Order.Status.SHIPPED: [Order.Status.OUT_FOR_DELIVERY],
    Order.Status.OUT_FOR_DELIVERY: [Order.Status.DELIVERED],
    Order.Status.DELIVERED: [Order.Status.RETURNED],
    Order.Status.RETURNED: [Order.Status.REFUNDED],
}


def _mark_cod_paid(order):
    """Settle a cash-on-delivery order once the parcel is delivered."""
    if order.is_paid or order.payment_method != "cod":
        return
    from apps.payments.models import Payment

    order.payment_status = "paid"
    order.save(update_fields=["payment_status"])
    Payment.objects.filter(order=order, provider="cod").update(
        status=Payment.Status.PAID, paid_at=timezone.now()
    )


@transaction.atomic
def transition_status(order, new_status, actor=None, note="", payment_status=None):
    """Move an order to a new status with history + side effects."""
    valid_targets = ALLOWED_TRANSITIONS.get(order.status, [])
    if new_status != order.status and new_status not in valid_targets:
        # Allow staff to jump within fulfilment states explicitly.
        if new_status not in Order.FULFILMENT_STATUSES + (
            Order.Status.CANCELLED, Order.Status.REFUNDED, Order.Status.RETURNED,
        ):
            raise ValidationError(
                _("Cannot move order from “%(from)s” to “%(to)s”.")
                % {
                    "from": order.get_status_display(),
                    "to": dict(Order.Status.choices)[new_status],
                }
            )

    old = order.status
    order.status = new_status
    if payment_status:
        order.payment_status = payment_status
    if new_status == Order.Status.DELIVERED:
        order.delivered_at = timezone.now()
    order.save()

    # Cash on delivery is settled when the parcel is delivered.
    if new_status == Order.Status.DELIVERED:
        _mark_cod_paid(order)

    OrderStatusHistory.objects.create(
        order=order,
        from_status=old,
        to_status=new_status,
        note=note,
        actor=actor,
    )

    if new_status in (Order.Status.CANCELLED, Order.Status.REFUNDED):
        for item in order.items.all():
            release_stock(
                product_id=item.product_id,
                variant_id=item.variant_id,
                quantity=item.quantity,
                reference=order.order_number,
                transaction_type="cancellation",
                note=note or new_status,
            )
        if new_status == Order.Status.CANCELLED and order.coupon:
            # Free the coupon slot: drop the redemption and recompute usage.
            CouponRedemption.objects.filter(order=order).delete()
            Coupon.objects.filter(pk=order.coupon_id).update(
                used_count=CouponRedemption.objects.filter(
                    coupon=order.coupon
                ).count()
            )

        # Auto-refund if order was paid
        if order.is_paid:
            try:
                from apps.payments.services import RefundService
                RefundService.refund_order(order, reason=note or new_status, actor=actor)
            except Exception as exc:
                # Log but don't block the status transition
                logger.warning(
                    "Auto-refund failed for order %s: %s. Manual refund may be needed.",
                    order.order_number, exc
                )

    _after_transition(order, new_status, actor)
    return order


def _after_transition(order, status, actor):
    from apps.notifications.email import send_order_email

    kind_by_status = {
        Order.Status.CONFIRMED: "processing",
        Order.Status.SHIPPED: "shipped",
        Order.Status.DELIVERED: "delivered",
        Order.Status.CANCELLED: "cancelled",
        Order.Status.REFUNDED: "refunded",
    }
    if status in kind_by_status and order.user:
        send_order_email(order, kind_by_status[status])

    if order.user is not None:
        Notification.objects.create(
            user=order.user,
            type=Notification.Type.ORDER,
            title=_("%(number)s: %(status)s")
            % {"number": order.order_number, "status": dict(Order.Status.choices)[status]},
            body=_("Your order is now %(status)s.")
            % {"status": dict(Order.Status.choices)[status].lower()},
            link=f"/orders/{order.order_number}/",
        )


# --------------------------------------------------------------------------
# Return/Refund Services
# --------------------------------------------------------------------------
class ReturnError(Exception):
    """User-facing return error."""
    pass


@transaction.atomic
def create_return_request(order, user, items_data, reason, reason_detail=""):
    """
    Create a return request for an order.
    
    items_data: list of dicts with {order_item_id, quantity, reason, reason_detail, restock}
    """
    from .models import ReturnRequest, ReturnItem, OrderItem
    
    # Verify order eligibility
    if order.status != Order.Status.DELIVERED:
        raise ReturnError(_("Only delivered orders can be returned."))
    
    if not order.is_paid:
        raise ReturnError(_("Only paid orders can be returned."))
    
    # Check if items already have pending returns
    for item_data in items_data:
        order_item = OrderItem.objects.get(pk=item_data["order_item_id"], order=order)
        existing_returns = ReturnItem.objects.filter(
            order_item=order_item,
            return_request__status__in=[
                ReturnRequest.Status.REQUESTED,
                ReturnRequest.Status.APPROVED,
                ReturnRequest.Status.RECEIVED,
            ]
        ).aggregate(total=models.Sum("quantity"))["total"] or 0
        
        available = order_item.quantity - existing_returns
        if item_data["quantity"] > available:
            raise ReturnError(
                _("Only %(count)s of “%(product)s” available for return.")
                % {"count": available, "product": order_item.product_name}
            )
    
    # Create return request
    return_request = ReturnRequest.objects.create(
        order=order,
        user=user,
        reason=reason,
        reason_detail=reason_detail,
        status=ReturnRequest.Status.REQUESTED,
    )
    
    # Create return items
    for item_data in items_data:
        order_item = OrderItem.objects.get(pk=item_data["order_item_id"], order=order)
        ReturnItem.objects.create(
            return_request=return_request,
            order_item=order_item,
            quantity=item_data["quantity"],
            reason=item_data.get("reason", reason),
            reason_detail=item_data.get("reason_detail", ""),
            restock=item_data.get("restock", True),
        )
    
    # Calculate total refund amount
    return_request.calculate_refund_amount()
    
    # Notify customer
    _notify_return_created(return_request)
    
    # Notify admins
    _notify_admins_return(return_request)
    
    return return_request


@transaction.atomic
def approve_return(return_request, actor, note=""):
    """Approve a return request — customer can now ship items back."""
    from .models import ReturnRequest
    
    if return_request.status != ReturnRequest.Status.REQUESTED:
        raise ReturnError(_("Only requested returns can be approved."))
    
    return_request.status = ReturnRequest.Status.APPROVED
    return_request.admin_note = note
    return_request.approved_at = timezone.now()
    return_request.save(update_fields=["status", "admin_note", "approved_at", "updated_at"])
    
    # Notify customer with return instructions
    _notify_return_approved(return_request)
    
    return return_request


@transaction.atomic
def reject_return(return_request, actor, note=""):
    """Reject a return request."""
    from .models import ReturnRequest
    
    if return_request.status != ReturnRequest.Status.REQUESTED:
        raise ReturnError(_("Only requested returns can be rejected."))
    
    return_request.status = ReturnRequest.Status.REJECTED
    return_request.admin_note = note
    return_request.save(update_fields=["status", "admin_note", "updated_at"])
    
    _notify_return_rejected(return_request)
    return return_request


@transaction.atomic
def receive_return(return_request, actor, tracking_number="", carrier="", note=""):
    """Mark return as received at warehouse — triggers refund."""
    from .models import ReturnRequest
    
    if return_request.status != ReturnRequest.Status.APPROVED:
        raise ReturnError(_("Only approved returns can be received."))
    
    return_request.status = ReturnRequest.Status.RECEIVED
    return_request.tracking_number = tracking_number
    return_request.carrier = carrier
    return_request.received_at = timezone.now()
    if note:
        return_request.admin_note = note
    return_request.save(update_fields=[
        "status", "tracking_number", "carrier", "received_at", "admin_note", "updated_at"
    ])
    
    # Restock items
    for item in return_request.items.all():
        if item.restock:
            from apps.inventory.services import restock
            restock(
                product_id=item.order_item.product_id,
                variant_id=item.order_item.variant_id,
                quantity=item.quantity,
                reference=f"return:{return_request.pk}",
                transaction_type="return",
                note=_("Return #%(pk)s received") % {"pk": return_request.pk},
            )
    
    # Process refund
    if return_request.refund_amount > 0:
        try:
            from apps.payments.services import RefundService
            RefundService.refund_order(
                return_request.order,
                amount=return_request.refund_amount,
                reason=_("Return #%(pk)s") % {"pk": return_request.pk},
                actor=actor,
            )
        except Exception as exc:
            logger.error("Refund failed for return %s: %s", return_request.pk, exc)
            # Don't block - admin can manually refund
    
    return_request.status = ReturnRequest.Status.REFUNDED
    return_request.refunded_at = timezone.now()
    return_request.save(update_fields=["status", "refunded_at", "updated_at"])
    
    # Update order status if fully returned
    _check_order_fully_returned(return_request.order)
    
    _notify_return_refunded(return_request)
    return return_request


@transaction.atomic
def cancel_return(return_request, actor):
    """Customer cancels their return request."""
    from .models import ReturnRequest
    
    if not return_request.can_customer_cancel:
        raise ReturnError(_("This return can no longer be cancelled."))
    
    return_request.status = ReturnRequest.Status.CANCELLED
    return_request.save(update_fields=["status", "updated_at"])
    
    _notify_return_cancelled(return_request)
    return return_request


def _check_order_fully_returned(order):
    """If all items returned, update order status to RETURNED."""
    total_qty = sum(item.quantity for item in order.items.all())
    returned_qty = ReturnItem.objects.filter(
        return_request__order=order,
        return_request__status__in=[
            ReturnRequest.Status.RECEIVED,
            ReturnRequest.Status.REFUNDED,
        ]
    ).aggregate(total=models.Sum("quantity"))["total"] or 0
    
    if returned_qty >= total_qty:
        order.status = Order.Status.RETURNED
        order.save(update_fields=["status"])


def _notify_return_created(return_request):
    from apps.notifications.email import send_order_email
    from apps.notifications.models import Notification
    
    if return_request.user:
        send_order_email(return_request.order, "return_requested")
        Notification.objects.create(
            user=return_request.user,
            type=Notification.Type.ORDER,
            title=_("Return requested for %(number)s")
            % {"number": return_request.order.order_number},
            body=_("We received your return request. Refund amount: %(amount)s.")
            % {"amount": return_request.refund_amount},
            link=f"/orders/{return_request.order.order_number}/",
        )


def _notify_return_approved(return_request):
    from apps.notifications.email import send_order_email
    from apps.notifications.models import Notification
    
    if return_request.user:
        send_order_email(return_request.order, "return_approved")
        Notification.objects.create(
            user=return_request.user,
            type=Notification.Type.ORDER,
            title=_("Return approved for %(number)s")
            % {"number": return_request.order.order_number},
            body=_("Your return was approved. Please ship items to our warehouse."),
            link=f"/orders/{return_request.order.order_number}/",
        )


def _notify_return_rejected(return_request):
    from apps.notifications.models import Notification
    
    if return_request.user:
        Notification.objects.create(
            user=return_request.user,
            type=Notification.Type.ORDER,
            title=_("Return rejected for %(number)s")
            % {"number": return_request.order.order_number},
            body=_("Your return request was rejected. Reason: %(reason)s")
            % {"reason": return_request.admin_note},
            link=f"/orders/{return_request.order.order_number}/",
        )


def _notify_return_refunded(return_request):
    from apps.notifications.models import Notification
    
    if return_request.user:
        Notification.objects.create(
            user=return_request.user,
            type=Notification.Type.ORDER,
            title=_("Refund processed for %(number)s")
            % {"number": return_request.order.order_number},
            body=_("Your refund of %(amount)s has been processed.")
            % {"amount": return_request.refund_amount},
            link=f"/orders/{return_request.order.order_number}/",
        )


def _notify_return_cancelled(return_request):
    from apps.notifications.models import Notification
    
    if return_request.user:
        Notification.objects.create(
            user=return_request.user,
            type=Notification.Type.ORDER,
            title=_("Return cancelled for %(number)s")
            % {"number": return_request.order.order_number},
            body=_("Your return request was cancelled."),
            link=f"/orders/{return_request.order.order_number}/",
        )


def _notify_admins_return(return_request):
    from django.contrib.auth import get_user_model
    from apps.notifications.models import Notification
    from django.contrib.contenttypes.models import ContentType
    
    User = get_user_model()
    recipients = User.objects.filter(
        role__in=[User.Role.ADMIN, User.Role.STAFF], is_active=True
    )
    ct = ContentType.objects.get_for_model(ReturnRequest)
    for admin in recipients:
        Notification.objects.create(
            user=admin,
            type=Notification.Type.SYSTEM,
            title=_("New return request #%(id)s") % {"id": return_request.pk},
            body=_("Order %(number)s · %(amount)s · %(count)s item(s)")
            % {
                "number": return_request.order.order_number,
                "amount": return_request.refund_amount,
                "count": return_request.items.count(),
            },
            link=f"/management/returns/{return_request.pk}/",
            content_type=ct,
            object_id=return_request.pk,
        )

