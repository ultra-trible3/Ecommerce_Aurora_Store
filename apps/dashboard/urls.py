"""Management portal URL configuration (/management/)."""
from django.urls import path

from . import (
    views_banners,
    views_catalog,
    views_home,
    views_ops,
    views_orders,
    views_people,
    views_promos,
    views_reports,
)

app_name = "dashboard"

urlpatterns = [
    # Overview
    path("", views_home.home, name="home"),

    # Catalog
    path("products/", views_catalog.products, name="products"),
    path("products/new/", views_catalog.product_create, name="product_create"),
    path("products/<int:pk>/", views_catalog.product_detail,name="product_detail",),
    path("products/<int:pk>/edit/", views_catalog.product_edit,name="product_edit",),
    path("products/<int:pk>/archive/", views_catalog.product_archive,name="product_archive",),
    
    path("categories/", views_catalog.categories, name="categories"),
    path("categories/new/", views_catalog.category_edit,name="category_create",),
    path("categories/<int:pk>/edit/", views_catalog.category_edit,name="category_edit",),
    path("categories/<int:pk>/toggle/", views_catalog.category_toggle,name="category_toggle",),
    
    path("brands/", views_catalog.brands, name="brands"),
    path("brands/new/", views_catalog.brand_edit, name="brand_create"),
    path("brands/<int:pk>/edit/", views_catalog.brand_edit, name="brand_edit"),
    path("brands/<int:pk>/toggle/", views_catalog.brand_toggle,name="brand_toggle",),

    # Orders
    path("orders/", views_orders.orders, name="orders"),
    # Exports must precede orders/<str:order_number>/ or "export" matches as an order number.
    path("orders/export/", views_orders.orders_export, name="orders_export"),
    path("orders/export/items/", views_orders.order_items_export, name="order_items_export"),
    path("orders/export/returns/", views_orders.returns_export, name="returns_export"),
    path("orders/<str:order_number>/", views_orders.order_detail,name="order_detail",),
    path("orders/<str:order_number>/edit/", views_orders.order_edit, name="order_edit"),
    path("orders/<str:order_number>/delete/", views_orders.order_delete, name="order_delete"),
    path("orders/<str:order_number>/status/", views_orders.order_status,name="order_status",),
    path("orders/<str:order_number>/payment/", views_orders.order_payment,name="order_payment",),
    path("orders/<str:order_number>/refund/", views_orders.order_refund,name="order_refund",),
    path("orders/<str:order_number>/cancel/", views_orders.order_cancel_admin,name="order_cancel_admin",),
    path("orders/<str:order_number>/invoice/", views_orders.order_invoice,name="order_invoice",),
    
    # Returns
    path("returns/", views_orders.returns_list, name="returns"),
    path("returns/export/", views_orders.returns_export, name="returns_export"),
    path("returns/<int:pk>/", views_orders.return_detail, name="return_detail"),
    path("returns/<int:pk>/approve/", views_orders.return_approve, name="return_approve"),
    path("returns/<int:pk>/reject/", views_orders.return_reject, name="return_reject"),
    path("returns/<int:pk>/receive/", views_orders.return_receive, name="return_receive"),

    # People
    path("customers/", views_people.customers, name="customers"),
    path("customers/<int:pk>/", views_people.customer_detail,name="customer_detail",),
    path("customers/<int:pk>/edit/", views_people.customer_edit, name="customer_edit"),
    path("customers/<int:pk>/delete/", views_people.customer_delete, name="customer_delete"),
    path("customers/<int:pk>/toggle/", views_people.customer_toggle,name="customer_toggle",),
    
    path("subscribers/", views_people.subscribers, name="subscribers"),
    path("subscribers/<int:pk>/toggle/", views_people.subscriber_toggle,name="subscriber_toggle",),
    
    path("notifications/", views_people.notifications, name="notifications",),
    path("notifications/<int:pk>/read/", views_people.notification_read,name="notification_read",),
    path("notifications/read-all/", views_people.notification_read_all,name="notification_read_all",),

    # Promotions & content
    path("coupons/", views_promos.coupons, name="coupons"),
    path("coupons/new/", views_promos.coupon_edit, name="coupon_create"),
    path("coupons/<int:pk>/edit/", views_promos.coupon_edit,name="coupon_edit",),
    path("coupons/<int:pk>/delete/", views_promos.coupon_delete,name="coupon_delete",),
    
    path("reviews/", views_promos.reviews, name="reviews"),
    path("reviews/<int:pk>/moderate/", views_promos.review_moderate,name="review_moderate",),

    # Banners & Advertisements
    path("banners/", views_banners.banners, name="banners"),
    path("banners/new/", views_banners.banner_create, name="banner_create"),
    path("banners/<int:pk>/edit/", views_banners.banner_edit, name="banner_edit"),
    path("banners/<int:pk>/delete/", views_banners.banner_delete, name="banner_delete"),
    path("banners/<int:pk>/preview/", views_banners.banner_preview, name="banner_preview"),

    # Operations
    path("inventory/", views_ops.inventory, name="inventory"),
    path("inventory/movements/", views_ops.stock_movements, name="inventory_movements"),
    path("inventory/adjust/", views_ops.inventory_adjust,name="inventory_adjust",),
    path("audit/", views_ops.audit_log, name="audit_log"),

    # Reports
    path("reports/", views_reports.reports, name="reports"),
    path("reports/sales/", views_reports.reports_sales, name="reports_sales"),
    path("reports/categories/", views_reports.reports_categories, name="reports_categories"),
    path("reports/customers/", views_reports.reports_customers, name="reports_customers"),
    path("reports/products/", views_reports.reports_products, name="reports_products"),
    path("reports/export/", views_reports.reports_export, name="reports_export"),
    path("reports/pdf/", views_reports.reports_pdf, name="reports_pdf"),
    path("reports/sales/pdf/", views_reports.reports_sales_pdf, name="reports_sales_pdf"),
    path("reports/categories/pdf/", views_reports.reports_categories_pdf, name="reports_categories_pdf"),
    path("reports/customers/pdf/", views_reports.reports_customers_pdf, name="reports_customers_pdf"),
    path("reports/products/pdf/", views_reports.reports_products_pdf, name="reports_products_pdf"),

    # System
    path("settings/", views_promos.settings, name="settings"),
]