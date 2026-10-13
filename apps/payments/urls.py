from django.urls import path

from . import views

app_name = "payments"

urlpatterns = [
    path("stripe/<str:order_number>/", views.stripe_pay, name="stripe_pay"),
    path("stripe/<str:order_number>/confirm/", views.stripe_confirm, name="stripe_confirm"),
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
    path("paypal/return/<str:order_number>/", views.paypal_return, name="paypal_return"),
    path("paypal/cancel/<str:order_number>/", views.paypal_cancel, name="paypal_cancel"),
]
