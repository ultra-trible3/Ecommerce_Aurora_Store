"""Template context processors for banners."""
import django.db.models as models
from django.utils import timezone

from apps.banners.models import Banner


def _active_queryset():
    return (
        Banner.objects.filter(
            is_active=True,
            valid_from__lte=timezone.now(),
        )
        .filter(
            models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=timezone.now())
        )
        .order_by("-position", "-created_at")
    )


def active_banners(request):
    """Return active banners for the storefront.

    Context:
        banners      -- list of active non-popup banners (hero slider slides)
        popup_banner -- active banner flagged as the deal popup (or None)
        active_banner-- first active banner of any kind (backwards compatible)

    The popup intentionally ignores the server-side show-once-per-session
    flag: the client gates it with sessionStorage and re-arms it after
    login/registration so it can greet the visitor again.
    """
    try:
        # Attach request metadata for targeting
        request.is_mobile = getattr(request, "is_mobile", False)
        request.country_code = getattr(request, "country_code", None)

        slides = []
        popup = None
        first = None

        for banner in _active_queryset():
            if banner.is_popup:
                if banner.matches_request(request, skip_session_check=True):
                    popup = popup or banner
                    first = first or banner
            elif banner.matches_request(request):
                slides.append(banner)
                first = first or banner

        return {
            "banners": slides,
            "popup_banner": popup,
            "active_banner": first,
        }
    except Exception:
        return {"banners": [], "popup_banner": None, "active_banner": None}
