"""Read-side queries powering the management dashboard."""
from datetime import timedelta
from decimal import Decimal
import logging

from django.db.models import Count, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.inventory.models import StockTransaction
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.reviews.models import Review


def store_stats():
    """Headline numbers for the overview cards."""
    today = timezone.now().date()
    month_start = today.replace(day=1)
    paid = Payment.objects.filter(status=Payment.Status.PAID)

    revenue_total = (
        Order.objects.exclude(
            status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED]
        ).aggregate(v=Sum("total"))["v"]
        or Decimal("0")
    )
    revenue_month = (
        Order.objects.filter(created_at__date__gte=month_start).exclude(
            status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED]
        ).aggregate(v=Sum("total"))["v"]
        or Decimal("0")
    )
    revenue_paid = paid.aggregate(v=Sum("amount"))["v"] or Decimal("0")

    return {
        "revenue_total": revenue_total,
        "revenue_month": revenue_month,
        "revenue_paid": revenue_paid,
        "orders_total": Order.objects.count(),
        "orders_month": Order.objects.filter(created_at__date__gte=month_start).count(),
        "orders_today": Order.objects.filter(created_at__date=today).count(),
        "orders_pending": Order.objects.filter(
            status__in=Order.ACTIVE_STATUSES
        ).count(),
        "awaiting_reviews": Review.objects.filter(
            status=Review.Status.PENDING
        ).count(),
    }


def dashboard_stats(user=None):
    """Store stats plus staff-specific counters."""
    from django.contrib.auth import get_user_model

    from apps.notifications.models import Notification

    stats = store_stats()
    User = get_user_model()
    today = timezone.now().date()
    month_start = today.replace(day=1)

    stats["customers_total"] = User.objects.filter(
        role=User.Role.CUSTOMER
    ).count()
    stats["customers_month"] = User.objects.filter(
        role=User.Role.CUSTOMER, date_joined__date__gte=month_start
    ).count()
    if user is not None and user.is_authenticated:
        stats["unread_notifications"] = Notification.objects.filter(
            user=user, is_read=False
        ).count()
    return stats


def revenue_series(days=14):
    """Daily revenue for the chart (non-cancelled orders)."""
    start = timezone.now().date() - timedelta(days=days - 1)
    rows = (
        Order.objects.filter(created_at__date__gte=start)
        .exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("total"))
        .order_by("day")
    )
    mapped = {row["day"]: row["total"] for row in rows}
    out = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        value = mapped.get(day)
        out.append({
            "label": day.strftime("%b %d"),
            "value": float(value) if value is not None else 0.0,
        })
    return out


def order_status_breakdown():
    rows = (
        Order.objects.values("status")
        .annotate(count=Count("id"))
        .order_by("-count")
    )
    labels = dict(Order.Status.choices)
    return [
        {"code": row["status"], "label": labels.get(row["status"], row["status"]),
         "count": row["count"]}
        for row in rows
    ]


def monthly_revenue(months=6):
    start = timezone.now().date().replace(day=1)
    # Walk back N-1 months.
    for _ in range(months - 1):
        start = (start - timedelta(days=1)).replace(day=1)
    rows = (
        Order.objects.filter(created_at__date__gte=start)
        .exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Sum("total"))
        .order_by("month")
    )
    mapped = {row["month"]: row["total"] for row in rows}

    out = []
    cursor = start
    for _ in range(months):
        key = cursor
        value = mapped.get(key)
        if value is None:
            # TruncMonth returns datetime; match by year+month.
            value = next(
                (v for k, v in mapped.items()
                 if k.year == key.year and k.month == key.month),
                None,
            )
        out.append({
            "label": cursor.strftime("%b %Y"),
            "value": float(value) if value is not None else 0.0,
        })
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def low_stock_products(limit=8):
    from apps.catalog.models import Product

    return (
        Product.objects.filter(status=Product.Status.ACTIVE)
        .filter(stock_quantity__lte=5)
        .order_by("stock_quantity")[:limit]
    )


def pending_reviews(limit=8):
    return (
        Review.objects.filter(status=Review.Status.PENDING)
        .select_related("product", "user")
        .order_by("-created_at")[:limit]
    )


def recent_stock_movements(limit=10):
    return (
        StockTransaction.objects.select_related(
            "product", "variant", "created_by"
        )
        .order_by("-created_at")[:limit]
    )


# --------------------------------------------------------------------------
# Admin Audit Logging
# --------------------------------------------------------------------------
logger = logging.getLogger(__name__)


class AuditLog:
    """Service for logging admin actions."""
    
    ACTION_TYPES = [
        ("create", _("Created")),
        ("update", _("Updated")),
        ("delete", _("Deleted")),
        ("status_change", _("Status Changed")),
        ("payment", _("Payment Action")),
        ("refund", _("Refund Processed")),
        ("cancel", _("Cancelled")),
        ("approve", _("Approved")),
        ("reject", _("Rejected")),
        ("login", _("Login")),
        ("export", _("Data Export")),
        ("settings", _("Settings Changed")),
        ("other", _("Other")),
    ]
    
    @staticmethod
    def log(
        user,
        action,
        object_type,
        object_id=None,
        object_repr="",
        changes=None,
        request=None,
        ip_address=None,
        user_agent=None,
    ):
        """
        Log an admin action.
        
        Args:
            user: User who performed the action
            action: Action type (create, update, delete, etc.)
            object_type: Model name (Order, Product, User, etc.)
            object_id: PK of the affected object
            object_repr: String representation of the object
            changes: Dict of field changes {field: {"old": val, "new": val}}
            request: HttpRequest for extracting IP/UA
        """
        from apps.dashboard.models import AdminAuditLog
        
        if request and not ip_address:
            xff = request.META.get("HTTP_X_FORWARDED_FOR")
            ip_address = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")
        
        if request and not user_agent:
            user_agent = request.META.get("HTTP_USER_AGENT", "")
        
        try:
            AdminAuditLog.objects.create(
                user=user,
                action=action,
                object_type=object_type,
                object_id=str(object_id) if object_id else "",
                object_repr=str(object_repr)[:200],
                changes=changes or {},
                ip_address=ip_address or "",
                user_agent=user_agent or "",
            )
        except Exception as exc:
            logger.error("Failed to write audit log: %s", exc)
            # Don't raise - audit logging should never break the main flow
    
    @staticmethod
    def log_model_change(user, instance, action, request=None, changed_fields=None):
        """Convenience method for model create/update/delete."""
        from django.forms.models import model_to_dict
        
        if changed_fields:
            changes = {}
            for field in changed_fields:
                old_val = getattr(instance, f"_old_{field}", None)
                new_val = getattr(instance, field, None)
                changes[field] = {"old": str(old_val) if old_val is not None else None, "new": str(new_val) if new_val is not None else None}
        else:
            changes = {}
        
        AuditLog.log(
            user=user,
            action=action,
            object_type=instance.__class__.__name__,
            object_id=instance.pk,
            object_repr=str(instance),
            changes=changes,
            request=request,
        )
    
    @staticmethod
    def log_order_status_change(user, order, old_status, new_status, note="", request=None):
        """Log order status transition."""
        AuditLog.log(
            user=user,
            action="status_change",
            object_type="Order",
            object_id=order.order_number,
            object_repr=f"Order {order.order_number}",
            changes={
                "status": {"old": old_status, "new": new_status},
                "note": note,
            },
            request=request,
        )
    
    @staticmethod
    def log_refund(user, order, amount, reason="", request=None):
        """Log refund processing."""
        AuditLog.log(
            user=user,
            action="refund",
            object_type="Order",
            object_id=order.order_number,
            object_repr=f"Order {order.order_number}",
            changes={
                "refund_amount": {"new": str(amount)},
                "reason": reason,
            },
            request=request,
        )
    
    @staticmethod
    def get_logs(
        user=None,
        action=None,
        object_type=None,
        object_id=None,
        date_from=None,
        date_to=None,
        limit=100,
    ):
        """Query audit logs with filters."""
        from apps.dashboard.models import AdminAuditLog
        
        qs = AdminAuditLog.objects.select_related("user")
        
        if user:
            qs = qs.filter(user=user)
        if action:
            qs = qs.filter(action=action)
        if object_type:
            qs = qs.filter(object_type=object_type)
        if object_id:
            qs = qs.filter(object_id=str(object_id))
        if date_from:
            qs = qs.filter(created_at__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__lte=date_to)
        
        return qs.order_by("-created_at")[:limit]


# --------------------------------------------------------------------------
# Enhanced Sales & Order Reports
# --------------------------------------------------------------------------
from decimal import Decimal
from datetime import timedelta
from django.db.models import Count, Sum, Avg, Q, F
from django.db.models.functions import TruncDate, TruncMonth, TruncWeek, TruncHour
from django.utils import timezone
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.catalog.models import Product


def date_range_from_request(request, default_days=30):
    """Parse date_from and date_to from request GET params."""
    today = timezone.now().date()
    default_start = today - timedelta(days=default_days)
    
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    
    if date_from:
        try:
            date_from = timezone.datetime.strptime(date_from, "%Y-%m-%d").date()
        except ValueError:
            date_from = default_start
    else:
        date_from = default_start
    
    if date_to:
        try:
            date_to = timezone.datetime.strptime(date_to, "%Y-%m-%d").date()
        except ValueError:
            date_to = today
    else:
        date_to = today
    
    return date_from, date_to


def sales_overview(request):
    """Complete sales overview with date range filtering."""
    date_from, date_to = date_range_from_request(request, default_days=30)
    
    # Base queryset for the period
    orders_qs = Order.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    ).exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])
    
    paid_qs = Payment.objects.filter(
        status=Payment.Status.PAID,
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    
    # KPIs
    total_revenue = orders_qs.aggregate(v=Sum("total"))["v"] or Decimal("0")
    total_orders = orders_qs.count()
    avg_order_value = orders_qs.aggregate(v=Avg("total"))["v"] or Decimal("0")
    paid_revenue = paid_qs.aggregate(v=Sum("amount"))["v"] or Decimal("0")
    conversion_rate = 0
    if total_orders > 0:
        conversion_rate = (orders_qs.filter(payment_status="paid").count() / total_orders) * 100
    
    # Daily revenue series
    daily_revenue = (
        orders_qs.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            revenue=Sum("total"),
            orders=Count("id"),
            aov=Avg("total"),
        )
        .order_by("day")
    )
    mapped = {row["day"]: row for row in daily_revenue}
    
    # Fill missing days
    series = []
    cursor = date_from
    while cursor <= date_to:
        row = mapped.get(cursor)
        series.append({
            "label": cursor.strftime("%b %d"),
            "date": cursor.isoformat(),
            "revenue": float(row["revenue"]) if row and row["revenue"] else 0.0,
            "orders": row["orders"] if row else 0,
            "aov": float(row["aov"]) if row and row["aov"] else 0.0,
        })
        cursor += timedelta(days=1)
    
    # Top products
    top_products = (
        orders_qs.values("items__product_name", "items__product_sku")
        .annotate(
            units_sold=Sum("items__quantity"),
            revenue=Sum("items__line_total"),
        )
        .order_by("-units_sold")[:10]
    )
    
    # Payment method breakdown
    payment_breakdown = (
        orders_qs.values("payment_method")
        .annotate(count=Count("id"), revenue=Sum("total"))
        .order_by("-count")
    )
    
    # Shipping method breakdown
    shipping_breakdown = (
        orders_qs.values("shipping_method_name", "shipping_method_code")
        .annotate(count=Count("id"), revenue=Sum("shipping_cost"))
        .order_by("-count")
    )
    
    # Hourly order distribution
    hourly_orders = (
        orders_qs.annotate(hour=TruncHour("created_at"))
        .values("hour")
        .annotate(count=Count("id"))
        .order_by("hour")
    )
    
    return {
        "date_from": date_from,
        "date_to": date_to,
        "kpis": {
            "total_revenue": total_revenue,
            "total_orders": total_orders,
            "avg_order_value": avg_order_value,
            "paid_revenue": paid_revenue,
            "conversion_rate": round(conversion_rate, 1),
        },
        "daily_series": series,
        "top_products": list(top_products),
        "payment_breakdown": list(payment_breakdown),
        "shipping_breakdown": list(shipping_breakdown),
        "hourly_orders": list(hourly_orders),
    }


def sales_by_category(request):
    """Sales breakdown by product category."""
    date_from, date_to = date_range_from_request(request, default_days=30)
    
    from apps.catalog.models import Category
    
    sales = (
        Order.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])
        .values("items__product__category__name", "items__product__category__slug")
        .annotate(
            revenue=Sum("items__line_total"),
            units=Sum("items__quantity"),
            orders=Count("id", distinct=True),
        )
        .order_by("-revenue")
    )
    
    return {
        "date_from": date_from,
        "date_to": date_to,
        "by_category": list(sales),
    }


def customer_analytics(request):
    """Customer acquisition and retention metrics."""
    date_from, date_to = date_range_from_request(request, default_days=90)
    
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    # New customers in period
    new_customers = User.objects.filter(
        role=User.Role.CUSTOMER,
        date_joined__date__gte=date_from,
        date_joined__date__lte=date_to,
    ).count()
    
    # Repeat customers (customers with >1 order in period)
    repeat_customers = (
        Order.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])
        .values("user_id")
        .annotate(order_count=Count("id"))
        .filter(order_count__gt=1)
        .count()
    )
    
    # Total unique customers who ordered
    total_ordering_customers = (
        Order.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])
        .values("user_id")
        .distinct()
        .count()
    )
    
    # Customer lifetime value (simplified - average revenue per customer)
    total_revenue = (
        Order.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])
        .aggregate(v=Sum("total"))["v"] or Decimal("0")
    )
    
    clv = total_revenue / total_ordering_customers if total_ordering_customers > 0 else Decimal("0")
    
    # Top customers by revenue
    top_customers = (
        Order.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])
        .values("user__email", "user__first_name", "user__last_name")
        .annotate(
            order_count=Count("id"),
            total_spent=Sum("total"),
            avg_order=Avg("total"),
        )
        .order_by("-total_spent")[:10]
    )
    
    return {
        "date_from": date_from,
        "date_to": date_to,
        "new_customers": new_customers,
        "repeat_customers": repeat_customers,
        "total_ordering_customers": total_ordering_customers,
        "customer_lifetime_value": clv,
        "repeat_rate": round((repeat_customers / total_ordering_customers * 100) if total_ordering_customers > 0 else 0, 1),
        "top_customers": list(top_customers),
    }


def product_performance(request):
    """Product-level performance metrics."""
    date_from, date_to = date_range_from_request(request, default_days=30)
    
    # Top selling products
    top_selling = (
        Order.objects.filter(
            created_at__date__gte=date_from,
            created_at__date__lte=date_to,
        )
        .exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED])
        .values("items__product_id", "items__product_name", "items__product_sku")
        .annotate(
            units_sold=Sum("items__quantity"),
            revenue=Sum("items__line_total"),
            orders=Count("id", distinct=True),
            avg_price=Avg("items__unit_price"),
        )
        .order_by("-units_sold")[:20]
    )
    
    # Low stock alerts
    low_stock = Product.objects.filter(
        status=Product.Status.ACTIVE,
        stock_quantity__lte=5,
    ).values("id", "name", "sku", "stock_quantity").order_by("stock_quantity")[:10]
    
    # Products with no sales in period
    sold_product_ids = set(s["items__product_id"] for s in top_selling)
    no_sales = Product.objects.filter(
        status=Product.Status.ACTIVE
    ).exclude(id__in=sold_product_ids).values("id", "name", "sku", "stock_quantity")[:10]
    
    return {
        "date_from": date_from,
        "date_to": date_to,
        "top_selling": list(top_selling),
        "low_stock": list(low_stock),
        "no_sales": list(no_sales),
    }