"""Catalog (storefront) URLs."""
from django.urls import path

from apps.catalog import views

app_name = "catalog"

urlpatterns = [
    path("shop/", views.shop, name="shop"),
    path("shop/category/<slug:slug>/", views.category, name="category"),
    path("shop/brand/<slug:slug>/", views.brand, name="brand"),
    path("product/<slug:slug>/", views.product_detail, name="detail"),
    path("product/<slug:slug>/notify/", views.stock_alert, name="stock_alert"),
    path("search/", views.search, name="search"),
    path("search/suggest/", views.search_suggest, name="suggest"),
    path("add-to-cart/", views.quick_add_to_cart, name="quick_add"),
    path("brands/", views.brand_list, name="brands"),
]
