"""Management portal: overview / home dashboard."""
from django.db.models import Sum
from django.shortcuts import render

from apps.orders.models import Order
from . import services
from .decorators import management_required


@management_required
def home(request):
    recent_orders = (
        Order.objects.select_related("user")
        .prefetch_related("items")
        .order_by("-created_at")[:8]
    )
    top_products = (
        Order.objects.exclude(
            status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED]
        )
        .values("items__product_name")
        .annotate(
            units_sold=Sum("items__quantity"),
            revenue=Sum("items__line_total"),
        )
        .order_by("-units_sold")[:6]
    )

    context = {
        "nav": "home",
        "stats": services.dashboard_stats(request.user),
        "revenue_series": services.revenue_series(14),
        "monthly_series": services.monthly_revenue(6),
        "status_breakdown": services.order_status_breakdown(),
        "recent_orders": recent_orders,
        "low_stock": services.low_stock_products(),
        "pending_reviews": services.pending_reviews(),
        "movements": services.recent_stock_movements(),
        "top_products": top_products,
    }
    return render(request, "management/home.html", context)
