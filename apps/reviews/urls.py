from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("create/<slug:slug>/", views.create, name="create"),
    path("<int:pk>/edit/", views.edit, name="edit"),
    path("<int:pk>/delete/", views.delete, name="delete"),
    path("ask/<slug:slug>/", views.ask_question, name="ask_question"),
]
