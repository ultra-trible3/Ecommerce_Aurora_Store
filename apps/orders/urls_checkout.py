from django.urls import path

from . import views_checkout

app_name = "checkout"

urlpatterns = [
    path("", views_checkout.start, name="start"),
    path("place-order/", views_checkout.place, name="place"),
]

