"""Customer-facing order views: list, detail, tracking, cancel, invoice, returns."""
import json
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.utils import paginate
from .models import Order, OrderItem, ReturnRequest, ReturnItem
from .services import OrderError, transition_status, create_return_request, cancel_return, ReturnError


def _get_order(request, order_number):
    order = get_object_or_404(
        Order.objects.prefetch_related(
            "items", "status_history", "payments"
        ),
        order_number=order_number,
    )
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        raise PermissionDenied(_("Sign in to view this order."))
    if order.user_id != user.pk and not user.is_management:
        raise PermissionDenied(_("This order does not belong to you."))
    return order


@login_required
def order_list(request):
    status_filter = request.GET.get("status", "")
    qs = Order.objects.filter(user=request.user).prefetch_related("items")
    if status_filter:
        qs = qs.filter(status=status_filter)
    page_obj = paginate(request, qs, per_page=10)
    context = {
        "page_obj": page_obj,
        "orders": page_obj.object_list,
        "status_filter": status_filter,
        "status_choices": Order.Status.choices,
        "active_count": Order.objects.filter(
            user=request.user, status__in=Order.ACTIVE_STATUSES
        ).count(),
    }
    return render(request, "orders/list.html", context)


def order_detail(request, order_number):
    order = _get_order(request, order_number)
    just_placed = request.session.get("last_order") == order.order_number
    if just_placed:
        request.session.pop("last_order", None)
    context = {
        "order": order,
        "items": order.items.all(),
        "history": order.status_history.all(),
        "steps": order.tracking_steps,
        "just_placed": just_placed,
        "payment": order.payments.order_by("-created_at").first(),
    }
    return render(request, "orders/detail.html", context)


@require_POST
def cancel_order(request, order_number):
    order = _get_order(request, order_number)
    if not order.can_cancel:
        messages.error(
            request,
            _("This order can no longer be cancelled. Contact support for help."),
        )
        return redirect("orders:detail", order_number=order_number)
    reason = request.POST.get("reason", "").strip()[:255]
    reason_category = request.POST.get("reason_category", "").strip()[:50]
    try:
        transition_status(
            order, Order.Status.CANCELLED, actor=request.user,
            note=reason or _("Cancelled by customer"),
        )
        # Store cancellation reason category
        if reason_category:
            order.cancel_reason_category = reason_category
            order.cancel_reason = reason
            order.cancelled_at = timezone.now()
            order.save(update_fields=["cancel_reason_category", "cancel_reason", "cancelled_at"])
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("orders:detail", order_number=order_number)
    messages.success(
        request, _("Order %(order)s cancelled.") % {"order": order.order_number}
    )
    return redirect("orders:detail", order_number=order_number)


@login_required
def invoice(request, order_number):
    order = _get_order(request, order_number)
    return render(request, "orders/invoice.html", {"order": order})


@login_required
def invoice_pdf(request, order_number):
    order = _get_order(request, order_number)
    try:
        from .invoice import render_invoice_pdf
    except Exception:  # pragma: no cover
        return render(request, "orders/invoice.html", {"order": order})
    buffer = render_invoice_pdf(order)
    return FileResponse(
        buffer,
        as_attachment=True,
        filename=f"{order.order_number}.pdf",
        content_type="application/pdf",
    )


def track_order(request, order_number):
    """Public order tracking page.

    Access is granted when either:
    * the visitor is signed in as the order's owner (or management staff), or
    * the visitor verifies the email/phone on the order (query params, then
      remembered in the session for later visits).
    """
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "status_history", "payments"),
        order_number=order_number,
    )

    user = getattr(request, "user", None)
    signed_in = bool(user is not None and user.is_authenticated)
    owns_order = signed_in and order.user_id and order.user_id == user.pk
    is_staff = signed_in and user.is_management

    # Verify access via email or phone (query params or session)
    verify_email = request.GET.get("email", "").strip().lower()
    verify_phone = request.GET.get("phone", "").strip()

    session_key = f"track_verified_{order_number}"
    if owns_order or is_staff:
        # Signed in with the right account: no extra verification needed.
        request.session[session_key] = True
    elif not request.session.get(session_key):
        # Require verification on first visit
        if verify_email:
            if verify_email != order.email.strip().lower():
                return render(request, "orders/track.html", {
                    "order": order,
                    "error": _("Email does not match this order."),
                    "needs_verification": True,
                })
            request.session[session_key] = True
        elif verify_phone:
            # Normalize phone for comparison
            order_phone = "".join(c for c in (order.shipping_phone or order.guest_phone or "") if c.isdigit())
            input_phone = "".join(c for c in verify_phone if c.isdigit())
            if input_phone != order_phone:
                return render(request, "orders/track.html", {
                    "order": order,
                    "error": _("Phone number does not match this order."),
                    "needs_verification": True,
                })
            request.session[session_key] = True
        else:
            # First visit - show verification form
            return render(request, "orders/track.html", {
                "order": order,
                "needs_verification": True,
                "has_account": bool(order.user_id),
            })

    # Access granted - show tracking info
    context = {
        "order": order,
        "items": order.items.all(),
        "steps": order.tracking_steps,
        "payment": order.payments.order_by("-created_at").first(),
    }
    return render(request, "orders/track.html", context)


# --------------------------------------------------------------------------
# Return/Refund Views
# --------------------------------------------------------------------------
@login_required
def return_request(request, order_number):
    """Customer requests a return for a delivered order."""
    order = _get_order(request, order_number)
    
    if order.status != Order.Status.DELIVERED:
        messages.error(request, _("Only delivered orders can be returned."))
        return redirect("orders:detail", order_number=order_number)
    
    if not order.is_paid:
        messages.error(request, _("Only paid orders can be returned."))
        return redirect("orders:detail", order_number=order_number)
    
    # Check for existing pending return
    existing = order.return_requests.filter(
        status__in=[ReturnRequest.Status.REQUESTED, ReturnRequest.Status.APPROVED, ReturnRequest.Status.RECEIVED]
    ).first()
    if existing:
        messages.info(
            request,
            _("You already have a pending return (#%(pk)s).") % {"pk": existing.pk},
        )
        return redirect("orders:return_detail", order_number=order_number, return_id=existing.pk)
    
    if request.method == "POST":
        try:
            items_data = json.loads(request.POST.get("items_data", "[]"))
            reason = request.POST.get("reason", "")
            reason_detail = request.POST.get("reason_detail", "")
            
            if not items_data:
                raise ReturnError(_("Please select at least one item to return."))
            
            return_request = create_return_request(
                order, request.user, items_data, reason, reason_detail
            )
            messages.success(
                request,
                _("Return request #%(pk)s submitted. We'll review it shortly.")
                % {"pk": return_request.pk},
            )
            return redirect("orders:return_detail", order_number=order_number, return_id=return_request.pk)
        except ReturnError as exc:
            messages.error(request, str(exc))
        except Exception as exc:
            messages.error(request, _("An error occurred. Please try again."))
    
    # Get items eligible for return
    eligible_items = []
    for item in order.items.all():
        returned_qty = ReturnItem.objects.filter(
            order_item=item,
            return_request__status__in=[
                ReturnRequest.Status.REQUESTED,
                ReturnRequest.Status.APPROVED,
                ReturnRequest.Status.RECEIVED,
                ReturnRequest.Status.REFUNDED,
            ]
        ).aggregate(total=models.Sum("quantity"))["total"] or 0
        available = item.quantity - returned_qty
        if available > 0:
            eligible_items.append({
                "item": item,
                "available_qty": available,
            })
    
    context = {
        "order": order,
        "eligible_items": eligible_items,
        "return_reasons": ReturnRequest.Reason.choices,
    }
    return render(request, "orders/return_request.html", context)


@login_required
def return_detail(request, order_number, return_id):
    """View return request details."""
    order = _get_order(request, order_number)
    return_request = get_object_or_404(ReturnRequest, pk=return_id, order=order, user=request.user)
    
    context = {
        "order": order,
        "return_request": return_request,
        "items": return_request.items.select_related("order_item").all(),
    }
    return render(request, "orders/return_detail.html", context)


@login_required
@require_POST
def return_cancel(request, order_number, return_id):
    """Customer cancels their return request."""
    order = _get_order(request, order_number)
    return_request = get_object_or_404(ReturnRequest, pk=return_id, order=order, user=request.user)
    
    try:
        cancel_return(return_request, request.user)
        messages.success(request, _("Return request cancelled."))
    except ReturnError as exc:
        messages.error(request, str(exc))
    
    return redirect("orders:return_detail", order_number=order_number, return_id=return_id)
