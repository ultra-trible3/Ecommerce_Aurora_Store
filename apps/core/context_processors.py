"""Template context processors."""
from django.conf import settings
from django.core.cache import cache
from django.utils.translation import gettext


def site_context(request):
    """Expose global site/branding values to every template."""
    from apps.core.cache_helpers import get_nav_categories

    unread = 0
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        try:
            from apps.notifications.models import Notification

            unread = Notification.objects.filter(user=user, is_read=False).count()
        except Exception:  # pragma: no cover - defensive
            unread = 0

    return {
        "SITE_NAME": settings.SITE_NAME,
        # SITE_TAGLINE may be a gettext_lazy default from settings; resolve it
        # against the request's active language so titles/og:description
        # render localized (the English source is the catalog msgid).
        "SITE_TAGLINE": gettext(str(settings.SITE_TAGLINE)),
        "SUPPORT_EMAIL": settings.SUPPORT_EMAIL,
        "SUPPORT_PHONE": settings.SUPPORT_PHONE,
        "SITE_URL": settings.SITE_URL,
        "CURRENCY_SYMBOL": settings.CURRENCY_SYMBOL,
        "TAX_RATE": settings.TAX_RATE,
        "STRIPE_PUBLIC_KEY": settings.STRIPE_PUBLIC_KEY,
        "unread_notifications": unread,
        "nav_categories": get_nav_categories(),
    }


def notifications_context(request):
    """Provide recent notifications for the dropdown (authenticated users)."""
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        try:
            notifications = user.notifications.all()[:10]
        except Exception:  # pragma: no cover - defensive
            notifications = []
    else:
        notifications = []
    return {"notifications": notifications}


def js_catalog(request):
    """Expose the client-side message catalog to every page.

    Translates each entry of ``JS_MESSAGES`` in the request's active language
    so ``window.t`` in ``templates/base.html`` can resolve every message.

    The map's *keys* are always the English source strings (what the JS code
    passes to ``window.t``/``window.ts``); the *values* are the localized
    forms.  ``str()`` on a ``gettext_lazy`` proxy resolves against the
    *currently active* language, so the keys are captured under the English
    locale first and only the values are translated per-request.  The
    template embeds the map with ``{% json_script %}`` (safe escaping), and
    JS falls back to the English source when a key is missing.
    """
    from django.utils import translation

    from apps.core.i18n_catalog import JS_MESSAGES

    with translation.override("en"):
        keys = [str(msg) for msg in JS_MESSAGES]
    return {"JS_CATALOG": {key: gettext(key) for key in keys}}
