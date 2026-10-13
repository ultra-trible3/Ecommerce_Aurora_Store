"""Banner app URLs."""
from django.urls import path

from . import views

app_name = "banners"

urlpatterns = [
    path("impression/<int:pk>/", views.track_impression, name="track_impression"),
    path("click/<int:pk>/", views.track_click, name="track_click"),
    path("seen/<int:pk>/", views.mark_seen, name="mark_seen"),
]