"""Sales and analytics reports with date-range filtering."""
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Sum, Count, Avg
from django.db.models.functions import TruncDate, TruncMonth, TruncHour
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.catalog.models import Product
from apps.orders.models import Order
from apps.payments.models import Payment
from . import services
from .decorators import management_required, permission_required


User = get_user_model()


@management_required
@permission_required("orders.view_order")
def reports(request):
    """Main reports dashboard with date range selector."""
    date_from, date_to = services.date_range_from_request(request, default_days=30)
    
    # Get all report data
    sales = services.sales_overview(request)
    categories = services.sales_by_category(request)
    customers = services.customer_analytics(request)
    products = services.product_performance(request)
    
    context = {
        "nav": "reports",
        "date_from": date_from,
        "date_to": date_to,
        "sales": sales,
        "categories": categories,
        "customers": customers,
        "products": products,
    }
    return render(request, "management/reports.html", context)


@management_required
@permission_required("orders.view_order")
def reports_sales(request):
    """Detailed sales report."""
    sales = services.sales_overview(request)
    
    context = {
        "nav": "reports",
        "date_from": sales["date_from"],
        "date_to": sales["date_to"],
        "kpis": sales["kpis"],
        "daily_series": sales["daily_series"],
        "top_products": sales["top_products"],
        "payment_breakdown": sales["payment_breakdown"],
        "shipping_breakdown": sales["shipping_breakdown"],
        "hourly_orders": sales["hourly_orders"],
    }
    return render(request, "management/reports/sales.html", context)


@management_required
@permission_required("orders.view_order")
def reports_categories(request):
    """Sales by category report."""
    categories = services.sales_by_category(request)
    
    context = {
        "nav": "reports",
        "date_from": categories["date_from"],
        "date_to": categories["date_to"],
        "by_category": categories["by_category"],
    }
    return render(request, "management/reports/categories.html", context)


@management_required
@permission_required("orders.view_order")
def reports_customers(request):
    """Customer analytics report."""
    customers = services.customer_analytics(request)
    
    context = {
        "nav": "reports",
        "date_from": customers["date_from"],
        "date_to": customers["date_to"],
        "new_customers": customers["new_customers"],
        "repeat_customers": customers["repeat_customers"],
        "total_ordering_customers": customers["total_ordering_customers"],
        "customer_lifetime_value": customers["customer_lifetime_value"],
        "repeat_rate": customers["repeat_rate"],
        "top_customers": customers["top_customers"],
    }
    return render(request, "management/reports/customers.html", context)


@management_required
@permission_required("orders.view_order")
def reports_products(request):
    """Product performance report."""
    products = services.product_performance(request)
    
    context = {
        "nav": "reports",
        "date_from": products["date_from"],
        "date_to": products["date_to"],
        "top_selling": products["top_selling"],
        "low_stock": products["low_stock"],
        "no_sales": products["no_sales"],
    }
    return render(request, "management/reports/products.html", context)


@management_required
@permission_required("orders.view_order")
def reports_export(request):
    """Export sales report to CSV."""
    from datetime import datetime
    import csv
    from django.http import HttpResponse
    
    date_from, date_to = services.date_range_from_request(request, default_days=365)
    
    orders_qs = Order.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    ).exclude(status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED]).select_related("user").prefetch_related("items")
    
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"sales_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow([
        _("Order Number"), _("Date"), _("Customer"), _("Email"),
        _("Status"), _("Payment Status"), _("Payment Method"),
        _("Shipping Method"), _("Shipping Cost"),
        _("Subtotal"), _("Discount"), _("Tax"), _("Total"),
        _("Coupon Code"), _("Items"),
    ])
    
    for order in orders_qs.iterator(chunk_size=100):
        writer.writerow([
            order.order_number,
            order.created_at.strftime("%Y-%m-%d %H:%M"),
            order.shipping_full_name,
            order.email,
            order.get_status_display(),
            order.get_payment_status_display(),
            order.payment_method,
            order.shipping_method_name,
            str(order.shipping_cost),
            str(order.subtotal),
            str(order.discount),
            str(order.tax),
            str(order.total),
            order.coupon_code or "",
            order.items.count(),
        ])
    
    return response


# --------------------------------------------------------------------------
# Report PDF downloads (branded, invoice-style)
# --------------------------------------------------------------------------
def _pdf_response(buffer, kind, date_from, date_to):
    """Stream a generated report buffer as a downloadable PDF."""
    from django.http import FileResponse

    filename = f"{kind}_{date_from:%Y%m%d}_{date_to:%Y%m%d}.pdf"
    return FileResponse(
        buffer,
        as_attachment=True,
        filename=filename,
        content_type="application/pdf",
    )


@management_required
@permission_required("orders.view_order")
def reports_pdf(request):
    """Download the overview report as a branded PDF."""
    from . import report_pdf

    buffer, date_from, date_to = report_pdf.render_overview_pdf(request)
    return _pdf_response(buffer, "reports", date_from, date_to)


@management_required
@permission_required("orders.view_order")
def reports_sales_pdf(request):
    """Download the detailed sales report as a branded PDF."""
    from . import report_pdf

    buffer, date_from, date_to = report_pdf.render_sales_pdf(request)
    return _pdf_response(buffer, "sales_report", date_from, date_to)


@management_required
@permission_required("orders.view_order")
def reports_categories_pdf(request):
    """Download the sales-by-category report as a branded PDF."""
    from . import report_pdf

    buffer, date_from, date_to = report_pdf.render_categories_pdf(request)
    return _pdf_response(buffer, "categories_report", date_from, date_to)


@management_required
@permission_required("orders.view_order")
def reports_customers_pdf(request):
    """Download the customer analytics report as a branded PDF."""
    from . import report_pdf

    buffer, date_from, date_to = report_pdf.render_customers_pdf(request)
    return _pdf_response(buffer, "customers_report", date_from, date_to)


@management_required
@permission_required("orders.view_order")
def reports_products_pdf(request):
    """Download the product performance report as a branded PDF."""
    from . import report_pdf

    buffer, date_from, date_to = report_pdf.render_products_pdf(request)
    return _pdf_response(buffer, "products_report", date_from, date_to)