"""Inventory: stock ledger and manual adjustments."""
from decimal import Decimal
import csv
from datetime import datetime

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalog.models import Product, product_name_q
from apps.core.utils import paginate
from apps.inventory import services as stock
from apps.inventory.models import StockTransaction
from apps.orders.models import Order
from .decorators import management_required, permission_required
from .forms import StockAdjustForm
from .models import AdminAuditLog
from .services import AuditLog

User = get_user_model()


@management_required
@permission_required("inventory.view_stocktransaction")
def inventory(request):
    products = Product.objects.all().order_by("name")
    q = (request.GET.get("q") or "").strip()
    if q:
        products = products.filter(product_name_q(q))
    state = request.GET.get("state", "")
    if state == "low":
        products = products.filter(
            stock_quantity__lte=5, status=Product.Status.ACTIVE
        )
    elif state == "out":
        products = products.filter(stock_quantity=0)
    elif state == "in":
        products = products.filter(stock_quantity__gt=5)

    page_obj = paginate(request, products, per_page=25)

    form = StockAdjustForm(initial={"product": request.GET.get("product")})
    if request.GET.get("product"):
        form.fields["product"].initial = request.GET.get("product")

    context = {
        "nav": "inventory",
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "q": q,
        "state": state,
        "form": form,
        "movements": StockTransaction.objects.select_related(
            "product", "variant", "created_by"
        ).order_by("-created_at")[:15],
        "totals": {
            "units": Product.objects.aggregate(
                total=Sum("stock_quantity")
            )["total"] or 0,
            "low": Product.objects.filter(
                stock_quantity__lte=5, stock_quantity__gt=0,
                status=Product.Status.ACTIVE,
            ).count(),
            "out": Product.objects.filter(stock_quantity=0).count(),
        },
    }
    return render(request, "management/inventory.html", context)


@management_required
@permission_required("inventory.view_stocktransaction")
def stock_movements(request):
    """Detailed stock movements history with filtering and pagination."""
    qs = StockTransaction.objects.select_related(
        "product", "variant", "created_by"
    ).order_by("-created_at")

    # Filters
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(product__sku__icontains=q) | qs.filter(product__name__icontains=q)

    txn_type = request.GET.get("type", "")
    if txn_type:
        qs = qs.filter(transaction_type=txn_type)

    product_id = request.GET.get("product")
    if product_id:
        qs = qs.filter(product_id=product_id)

    date_from = request.GET.get("date_from")
    if date_from:
        try:
            qs = qs.filter(created_at__date__gte=date_from)
        except ValueError:
            pass

    date_to = request.GET.get("date_to")
    if date_to:
        try:
            qs = qs.filter(created_at__date__lte=date_to)
        except ValueError:
            pass

    page_obj = paginate(request, qs, per_page=50)

    # Export
    if request.GET.get("export") == "csv":
        return _export_movements_csv(qs)

    context = {
        "nav": "inventory",
        "page_obj": page_obj,
        "movements": page_obj.object_list,
        "q": q,
        "txn_type": txn_type,
        "product_id": product_id,
        "date_from": date_from,
        "date_to": date_to,
        "types": StockTransaction.Type.choices,
        "products": Product.objects.filter(stock_transactions__isnull=False).distinct().order_by("name"),
    }
    return render(request, "management/inventory_movements.html", context)


def _export_movements_csv(qs):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"stock_movements_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow([
        _("Date"), _("Product"), _("SKU"), _("Variant"), _("Type"),
        _("Quantity"), _("Stock After"), _("Reference"), _("Note"),
        _("Created By"),
    ])

    for m in qs.iterator(chunk_size=100):
        writer.writerow([
            m.created_at.strftime("%Y-%m-%d %H:%M"),
            m.product.name,
            m.product.sku,
            m.variant.name if m.variant else "",
            m.get_transaction_type_display(),
            m.quantity,
            m.stock_after,
            m.reference,
            m.note,
            m.created_by.get_full_name() if m.created_by else "System",
        ])

    return response


@management_required
@permission_required("inventory.change_stocktransaction")
@require_POST
def inventory_adjust(request):
    form = StockAdjustForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Could not apply the stock adjustment."))
        return redirect("dashboard:inventory")

    product = form.cleaned_data["product"]
    variant_id = form.cleaned_data.get("variant_id")
    quantity = form.cleaned_data["quantity"]
    try:
        stock.adjust_stock(
            product_id=product.pk,
            variant_id=variant_id or None,
            quantity=quantity,
            adjustment_type=form.cleaned_data["transaction_type"],
            note=form.cleaned_data.get("note", ""),
            actor=request.user,
        )
    except stock.StockError as exc:
        messages.error(request, str(exc))
    else:
        sign = "+" if quantity > 0 else ""
        messages.success(
            request,
            _("%(product)s: %(sign)s%(quantity)s applied (now %(stock)s).")
            % {
                "product": product.name,
                "sign": sign,
                "quantity": quantity,
                "stock": product.stock_quantity,
            },
        )
    return redirect("dashboard:inventory")


# --------------------------------------------------------------------------
# Admin Audit Log
# --------------------------------------------------------------------------
@management_required
@permission_required("dashboard.view_adminauditlog")
def audit_log(request):
    """View admin audit logs with filtering."""
    user_filter = request.GET.get("user", "")
    action_filter = request.GET.get("action", "")
    object_type_filter = request.GET.get("object_type", "")
    object_id_filter = request.GET.get("object_id", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    
    qs = AdminAuditLog.objects.select_related("user").order_by("-created_at")
    
    if user_filter:
        qs = qs.filter(user_id=user_filter)
    if action_filter:
        qs = qs.filter(action=action_filter)
    if object_type_filter:
        qs = qs.filter(object_type__icontains=object_type_filter)
    if object_id_filter:
        qs = qs.filter(object_id__icontains=object_id_filter)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    
    # Export
    if request.GET.get("export") == "csv":
        return _export_audit_csv(qs)
    
    page_obj = paginate(request, qs, per_page=50)
    
    # Get distinct values for filters
    users = User.objects.filter(audit_logs__isnull=False).distinct()
    actions = AdminAuditLog.ACTION_TYPES = [
        ("create", _("Created")), ("update", _("Updated")), ("delete", _("Deleted")),
        ("status_change", _("Status Changed")), ("payment", _("Payment Action")),
        ("refund", _("Refund Processed")), ("cancel", _("Cancelled")),
        ("approve", _("Approved")), ("reject", _("Rejected")), ("login", _("Login")),
        ("export", _("Data Export")), ("settings", _("Settings Changed")),
        ("other", _("Other")),
    ]
    object_types = AdminAuditLog.objects.values_list("object_type", flat=True).distinct()
    
    context = {
        "nav": "audit",
        "page_obj": page_obj,
        "logs": page_obj.object_list,
        "users": users,
        "actions": actions,
        "object_types": object_types,
        "filters": {
            "user": user_filter,
            "action": action_filter,
            "object_type": object_type_filter,
            "object_id": object_id_filter,
            "date_from": date_from,
            "date_to": date_to,
        },
    }
    return render(request, "management/audit_log.html", context)


def _export_audit_csv(qs):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow([
        _("Date"), _("User"), _("Action"), _("Object Type"), _("Object ID"),
        _("Object"), _("Changes"), _("IP Address"),
    ])
    
    for log in qs.iterator(chunk_size=100):
        writer.writerow([
            log.created_at.strftime("%Y-%m-%d %H:%M"),
            log.user.get_full_name() if log.user else "System",
            log.action,
            log.object_type,
            log.object_id,
            log.object_repr,
            str(log.changes),
            log.ip_address or "",
        ])
    
    return response