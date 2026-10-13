from django.urls import path

from . import wishlist_views as views

app_name = "wishlist"

urlpatterns = [
    path("mini/", views.mini, name="mini"),
    path("toggle/", views.toggle, name="toggle"),
    path("<int:pk>/remove/", views.remove, name="remove"),
    path("<int:pk>/move/", views.move_to_cart, name="move"),
]

