"""Compare products URLs."""
from django.urls import path

from . import compare_views as views

app_name = "compare"
urlpatterns = [
    path("", views.list_view, name="list"),
    path("toggle/", views.toggle, name="toggle"),
    path("clear/", views.clear, name="clear"),
    path("<slug:slug>/remove/", views.remove, name="remove"),
]
