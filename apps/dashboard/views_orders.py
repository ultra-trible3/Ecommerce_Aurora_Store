"""Order management: fulfilment queue, detail view and status updates."""
import csv
from datetime import datetime

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.utils import paginate
from apps.orders.models import Order, OrderItem, ReturnRequest
from apps.orders.services import ALLOWED_TRANSITIONS, transition_status, approve_return, reject_return, receive_return, ReturnError
from .decorators import management_required, permission_required
from .forms import OrderEditForm

FILTERS = {
    "": {},
    "active": {"status__in": Order.ACTIVE_STATUSES},
    "pending": {"status": Order.Status.PENDING},
    "confirmed": {"status": Order.Status.CONFIRMED},
    "processing": {"status": Order.Status.PROCESSING},
    "shipped": {"status": Order.Status.SHIPPED},
    "delivered": {"status": Order.Status.DELIVERED},
    "cancelled": {"status": Order.Status.CANCELLED},
    "unpaid": {"payment_status__in": ["pending", "failed"]},
}


@management_required
@permission_required("orders.view_order")
def orders(request):
    status_filter = request.GET.get("status", "")
    qs = Order.objects.select_related("user").prefetch_related("items")

    if status_filter in FILTERS:
        qs = qs.filter(**FILTERS[status_filter])

    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(order_number__icontains=q)
            | Q(email__icontains=q)
            | Q(shipping_full_name__icontains=q)
        )

    payment = request.GET.get("payment", "")
    if payment:
        qs = qs.filter(payment_status=payment)

    page_obj = paginate(request, qs, per_page=20)
    context = {
        "nav": "orders",
        "page_obj": page_obj,
        "orders": page_obj.object_list,
        "q": q,
        "status_filter": status_filter,
        "payment_filter": payment,
        "filters": FILTERS,
        "status_choices": Order.Status.choices,
        "payment_choices": ["pending", "processing", "paid", "failed",
                            "refunded", "cancelled"],
        "active_count": Order.objects.filter(
            status__in=Order.ACTIVE_STATUSES
        ).count(),
    }
    return render(request, "management/orders/list.html", context)


@management_required
@permission_required("orders.view_order")
def order_detail(request, order_number):
    order = get_object_or_404(
        Order.objects.select_related("user", "coupon").prefetch_related(
            "items", "status_history", "payments"
        ),
        order_number=order_number,
    )
    history = list(order.status_history.all())
    allowed = ALLOWED_TRANSITIONS.get(order.status, [])
    context = {
        "nav": "orders",
        "order": order,
        "items": order.items.all(),
        "history": history,
        "allowed": [(code, dict(Order.Status.choices)[code]) for code in allowed],
        "payment": order.payments.order_by("-created_at").first(),
        "customer_orders": Order.objects.filter(user=order.user).exclude(
            pk=order.pk
        )[:6] if order.user_id else Order.objects.none(),
        "deletable": _is_deletable(order),
    }
    return render(request, "management/orders/detail.html", context)


def _is_deletable(order):
    """Paid or fulfilled orders keep their financial record (cancel instead)."""
    if order.is_paid:
        return False
    return order.status not in (Order.Status.SHIPPED, Order.Status.DELIVERED)


@management_required
@permission_required("orders.change_order")
@require_http_methods(["GET", "POST"])
def order_edit(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    form = OrderEditForm(request.POST or None, instance=order)
    if request.method == "POST" and form.is_valid():
        form.save()
        order.status_history.create(
            from_status=order.status,
            to_status=order.status,
            note=_("Order details updated"),
            actor=request.user,
            is_customer_visible=False,
        )
        messages.success(
            request,
            _("%(number)s updated.") % {"number": order.order_number},
        )
        return redirect("dashboard:order_detail", order_number=order.order_number)
    return render(
        request,
        "management/orders/form.html",
        {"nav": "orders", "order": order, "form": form},
    )


@management_required
@permission_required("orders.delete_order")
@require_POST
def order_delete(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    if not _is_deletable(order):
        messages.error(
            request,
            _(
                "%(number)s cannot be deleted because it is %(reason)s. "
                "Cancel it instead to keep the financial record."
            )
            % {
                "number": order.order_number,
                "reason": _("paid")
                if order.is_paid
                else order.get_status_display().lower(),
            },
        )
        return redirect("dashboard:order_detail", order_number=order.order_number)
    number = order.order_number
    order.delete()
    messages.success(
        request, _("Order %(number)s deleted.") % {"number": number}
    )
    return redirect("dashboard:orders")


@management_required
@permission_required("orders.change_order")
@require_POST
def order_status(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    new_status = request.POST.get("status", "")
    note = request.POST.get("note", "").strip()[:255]
    try:
        transition_status(order, new_status, actor=request.user, note=note)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    except Exception as exc:  # pragma: no cover - defensive
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            _("%(number)s → %(status)s.")
            % {
                "number": order.order_number,
                "status": order.get_status_display(),
            },
        )
    return redirect("dashboard:order_detail", order_number=order_number)


@management_required
@permission_required("orders.change_order")
@require_POST
def order_cancel_admin(request, order_number):
    """Admin override: cancel order even if outside customer cancellation window."""
    order = get_object_or_404(Order, order_number=order_number)

    if not order.can_cancel_admin:
        messages.error(
            request,
            _("Cannot cancel %(number)s — status is %(status)s.")
            % {
                "number": order.order_number,
                "status": order.get_status_display(),
            },
        )
        return redirect("dashboard:order_detail", order_number=order_number)

    reason = request.POST.get("reason", "").strip()[:255]
    reason_category = request.POST.get("reason_category", "").strip()[:50]
    note = f"[Admin] {reason or _('Cancelled by staff')}"
    
    try:
        transition_status(order, Order.Status.CANCELLED, actor=request.user, note=note)
        # Store cancellation reason category
        if reason_category:
            order.cancel_reason_category = reason_category
            order.cancel_reason = reason
            order.cancelled_at = timezone.now()
            order.save(update_fields=["cancel_reason_category", "cancel_reason", "cancelled_at"])
        messages.success(
            request,
            _("Order %(number)s cancelled by admin.")
            % {"number": order.order_number},
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    except Exception as exc:
        messages.error(
            request, _("Cancellation failed: %(error)s") % {"error": exc}
        )

    return redirect("dashboard:order_detail", order_number=order_number)


@management_required
@permission_required("orders.change_order")
@require_POST
def order_refund(request, order_number):
    """Process a refund for a paid order (full refund only)."""
    order = get_object_or_404(Order, order_number=order_number)

    if not order.is_paid:
        messages.error(request, _("Cannot refund an unpaid order."))
        return redirect("dashboard:order_detail", order_number=order_number)

    if order.status in (Order.Status.REFUNDED, Order.Status.CANCELLED):
        messages.error(request, _("Order already refunded or cancelled."))
        return redirect("dashboard:order_detail", order_number=order_number)

    try:
        from apps.payments.services import RefundService
        result = RefundService.refund_order(
            order, reason=_("Manual refund by staff"), actor=request.user
        )

        if result["status"] == "refunded":
            messages.success(
                request,
                _("Full refund processed for %(number)s.")
                % {"number": order.order_number},
            )
        elif result["status"] == "partial":
            messages.warning(
                request,
                _("Partial refund processed for %(number)s.")
                % {"number": order.order_number},
            )
        else:
            messages.error(
                request,
                _("Refund failed: %(error)s")
                % {"error": result.get("details", _("Unknown error"))},
            )

    except Exception as exc:
        messages.error(request, _("Refund failed: %(error)s") % {"error": exc})

    return redirect("dashboard:order_detail", order_number=order_number)


@management_required
@permission_required("orders.change_order")
@require_POST
def order_payment(request, order_number):
    """Manually mark an order paid (offline transfers, corrections)."""
    order = get_object_or_404(Order, order_number=order_number)
    action = request.POST.get("action", "")

    if action == "mark_paid":
        from django.utils import timezone

        from apps.payments.models import Payment

        order.payment_status = "paid"
        order.save(update_fields=["payment_status"])
        payment, _created = Payment.objects.get_or_create(
            order=order,
            provider="cod",
            defaults={"status": Payment.Status.PAID, "amount": order.total},
        )
        if payment.status != Payment.Status.PAID:
            payment.status = Payment.Status.PAID
            payment.paid_at = timezone.now()
            payment.save(update_fields=["status", "paid_at"])
        if order.status == Order.Status.PENDING:
            try:
                transition_status(
                    order, Order.Status.CONFIRMED,
                    actor=request.user, note=_("Marked paid by staff"),
                )
            except Exception:  # pragma: no cover
                pass
        messages.success(
            request,
            _("%(number)s marked as paid.") % {"number": order.order_number},
        )
    elif action == "mark_unpaid":
        order.payment_status = "pending"
        order.save(update_fields=["payment_status"])
        messages.info(
            request,
            _("%(number)s set to unpaid.") % {"number": order.order_number},
        )
    return redirect("dashboard:order_detail", order_number=order_number)


@management_required
@permission_required("orders.view_order")
def order_invoice(request, order_number):
    order = get_object_or_404(Order, order_number=order_number)
    return render(
        request, "management/orders/invoice.html",
        {"nav": "orders", "order": order},
    )


@management_required
@permission_required("orders.view_order")
def orders_export(request):
    """Export orders to CSV."""
    status_filter = request.GET.get("status", "")
    qs = Order.objects.select_related("user", "coupon").prefetch_related("items")

    if status_filter in FILTERS:
        qs = qs.filter(**FILTERS[status_filter])

    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(
            Q(order_number__icontains=q)
            | Q(email__icontains=q)
            | Q(shipping_full_name__icontains=q)
        )

    payment = request.GET.get("payment", "")
    if payment:
        qs = qs.filter(payment_status=payment)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"orders_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        _("Order Number"), _("Date"), _("Customer"), _("Email"), _("Phone"),
        _("Status"), _("Payment Status"), _("Payment Method"),
        _("Shipping Method"), _("Shipping Cost"),
        _("Subtotal"), _("Discount"), _("Tax"), _("Total"),
        _("Coupon Code"), _("Items Count"), _("Notes"),
    ])

    for order in qs.iterator(chunk_size=100):
        writer.writerow([
            order.order_number,
            order.created_at.strftime("%Y-%m-%d %H:%M"),
            order.shipping_full_name,
            order.email,
            order.shipping_phone,
            order.get_status_display(),
            order.get_payment_status_display(),
            order.get_payment_method_display() if hasattr(order, "get_payment_method_display") else order.payment_method,
            order.shipping_method_name,
            str(order.shipping_cost),
            str(order.subtotal),
            str(order.discount),
            str(order.tax),
            str(order.total),
            order.coupon_code or "",
            order.items.count(),
            order.notes.replace("\n", " ").replace("\r", " ") if order.notes else "",
        ])

    return response


@management_required
@permission_required("orders.view_order")
def order_items_export(request):
    """Export order line items to CSV (one row per item)."""
    status_filter = request.GET.get("status", "")
    qs = OrderItem.objects.select_related("order", "product", "variant")

    if status_filter in FILTERS:
        qs = qs.filter(order__status__in=FILTERS[status_filter].get("status__in", []))

    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(
            Q(order__order_number__icontains=q)
            | Q(order__email__icontains=q)
            | Q(product_name__icontains=q)
            | Q(product_sku__icontains=q)
        )

    payment = request.GET.get("payment", "")
    if payment:
        qs = qs.filter(order__payment_status=payment)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"order_items_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        _("Order Number"), _("Order Date"), _("Customer"), _("Email"),
        _("Product Name"), _("SKU"), _("Variant"), _("Quantity"),
        _("Unit Price"), _("Original Price"), _("Line Total"),
        _("Order Status"), _("Payment Status"),
    ])

    for item in qs.iterator(chunk_size=100):
        writer.writerow([
            item.order.order_number,
            item.order.created_at.strftime("%Y-%m-%d %H:%M"),
            item.order.shipping_full_name,
            item.order.email,
            item.display_name,
            item.product_sku,
            item.variant_name or "",
            item.quantity,
            str(item.unit_price),
            str(item.original_price),
            str(item.line_total),
            item.order.get_status_display(),
            item.order.get_payment_status_display(),
        ])

    return response


# --------------------------------------------------------------------------
# Return Management (Admin)
# --------------------------------------------------------------------------
@management_required
@permission_required("orders.view_order")
def returns_list(request):
    """List all return requests with filters."""
    status_filter = request.GET.get("status", "")
    qs = ReturnRequest.objects.select_related("order", "order__user", "user").prefetch_related("items")

    if status_filter:
        qs = qs.filter(status=status_filter)

    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(
            Q(order__order_number__icontains=q)
            | Q(user__email__icontains=q)
            | Q(pk__icontains=q)
        )

    page_obj = paginate(request, qs, per_page=20)
    context = {
        "nav": "orders",
        "page_obj": page_obj,
        "returns": page_obj.object_list,
        "q": q,
        "status_filter": status_filter,
        "status_choices": ReturnRequest.Status.choices,
    }
    return render(request, "management/returns/list.html", context)


@management_required
@permission_required("orders.view_order")
def return_detail(request, pk):
    """View return request details."""
    return_request = get_object_or_404(
        ReturnRequest.objects.select_related("order", "order__user", "user").prefetch_related("items__order_item"),
        pk=pk
    )
    
    context = {
        "nav": "orders",
        "return_request": return_request,
        "items": return_request.items.select_related("order_item").all(),
        "order": return_request.order,
        "status_choices": ReturnRequest.Status.choices,
    }
    return render(request, "management/returns/detail.html", context)


@management_required
@permission_required("orders.change_order")
@require_POST
def return_approve(request, pk):
    """Approve a return request."""
    return_request = get_object_or_404(ReturnRequest, pk=pk)
    note = request.POST.get("note", "").strip()
    
    try:
        from apps.orders.services import approve_return
        approve_return(return_request, request.user, note)
        messages.success(request, _("Return #%(pk)s approved.") % {"pk": pk})
    except ReturnError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        messages.error(request, _("Approval failed: %(error)s") % {"error": exc})
    
    return redirect("dashboard:return_detail", pk=pk)


@management_required
@permission_required("orders.change_order")
@require_POST
def return_reject(request, pk):
    """Reject a return request."""
    return_request = get_object_or_404(ReturnRequest, pk=pk)
    note = request.POST.get("note", "").strip()
    
    try:
        from apps.orders.services import reject_return
        reject_return(return_request, request.user, note)
        messages.success(request, _("Return #%(pk)s rejected.") % {"pk": pk})
    except ReturnError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        messages.error(request, _("Rejection failed: %(error)s") % {"error": exc})
    
    return redirect("dashboard:return_detail", pk=pk)


@management_required
@permission_required("orders.change_order")
@require_POST
def return_receive(request, pk):
    """Mark return as received and process refund."""
    return_request = get_object_or_404(ReturnRequest, pk=pk)
    tracking_number = request.POST.get("tracking_number", "").strip()
    carrier = request.POST.get("carrier", "").strip()
    note = request.POST.get("note", "").strip()
    
    try:
        from apps.orders.services import receive_return
        receive_return(return_request, request.user, tracking_number, carrier, note)
        messages.success(
            request,
            _("Return #%(pk)s received and refund processed.") % {"pk": pk},
        )
    except ReturnError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        messages.error(request, _("Receive failed: %(error)s") % {"error": exc})
    
    return redirect("dashboard:return_detail", pk=pk)


@management_required
@permission_required("orders.view_order")
def returns_export(request):
    """Export return requests to CSV."""
    status_filter = request.GET.get("status", "")
    qs = ReturnRequest.objects.select_related("order", "user")

    if status_filter:
        qs = qs.filter(status=status_filter)

    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(
            Q(order__order_number__icontains=q)
            | Q(user__email__icontains=q)
            | Q(pk__icontains=q)
        )

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"returns_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        _("Return ID"), _("Order Number"), _("Date"), _("Customer"), _("Email"),
        _("Status"), _("Reason"), _("Items"), _("Refund Amount"),
        _("Approved At"), _("Received At"), _("Refunded At"),
    ])

    for ret in qs.iterator(chunk_size=100):
        writer.writerow([
            ret.pk,
            ret.order.order_number,
            ret.created_at.strftime("%Y-%m-%d %H:%M"),
            ret.user.get_full_name() or ret.user.email,
            ret.user.email,
            ret.get_status_display(),
            ret.get_reason_display(),
            ret.items.count(),
            str(ret.refund_amount),
            ret.approved_at.strftime("%Y-%m-%d %H:%M") if ret.approved_at else "",
            ret.received_at.strftime("%Y-%m-%d %H:%M") if ret.received_at else "",
            ret.refunded_at.strftime("%Y-%m-%d %H:%M") if ret.refunded_at else "",
        ])

    return response
