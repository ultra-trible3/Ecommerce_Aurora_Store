from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("", views.order_list, name="list"),
    path("<str:order_number>/", views.order_detail, name="detail"),
    path("<str:order_number>/cancel/", views.cancel_order, name="cancel"),
    path("<str:order_number>/invoice/", views.invoice, name="invoice"),
    path("<str:order_number>/invoice/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("track/<str:order_number>/", views.track_order, name="track"),
    # Returns
    path("<str:order_number>/return/", views.return_request, name="return_request"),
    path("<str:order_number>/return/<int:return_id>/", views.return_detail, name="return_detail"),
    path("<str:order_number>/return/<int:return_id>/cancel/", views.return_cancel, name="return_cancel"),
]

