"""Root URL configuration."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import RedirectView

from apps.core.sitemaps import sitemaps

admin.site.site_header = "Aurora Store Administration"
admin.site.site_title = "Aurora Store admin"
admin.site.index_title = "Store management"

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    # Storefront
    path("", include("apps.core.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.banners.urls")),
    path("accounts/", include("apps.accounts.urls")),
    # Legacy page URLs — cart & wishlist now live in the header side drawer.
    path(
        "cart/",
        RedirectView.as_view(url="/", permanent=False),
        name="legacy_cart",
    ),
    path(
        "wishlist/",
        RedirectView.as_view(url="/", permanent=False),
        name="legacy_wishlist",
    ),
    path("cart/", include("apps.cart.urls")),
    path("wishlist/", include("apps.cart.urls_wishlist")),
    path("compare/", include("apps.cart.urls_compare")),
    path("checkout/", include("apps.orders.urls_checkout")),
    path("orders/", include("apps.orders.urls")),
    path("payments/", include("apps.payments.urls")),
    path("reviews/", include("apps.reviews.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("newsletter/", include("apps.notifications.urls_newsletter")),
    # Management portal
    path("management/", include("apps.dashboard.urls")),
    # SEO
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.sitemaps",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(
        settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0]
    )

handler400 = "apps.core.views.bad_request"
handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.page_not_found"
handler500 = "apps.core.views.server_error"
