"""Notification and newsletter views."""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from apps.core.utils import client_ip, throttle
from .models import Notification, NewsletterSubscriber


@require_GET
def list_view(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    items = request.user.notifications.all()[:50]
    return render(request, "notifications/list.html", {"notifications": items})


@require_GET
@never_cache
def poll(request):
    """Lightweight poll used by the header bell (new-notification chime)."""
    if not request.user.is_authenticated:
        return JsonResponse({"authenticated": False, "unread": 0, "latest_id": 0, "new": []})

    qs = request.user.notifications.all()
    unread = qs.filter(is_read=False).count()
    latest = qs.order_by("-pk").first()
    latest_id = latest.pk if latest else 0

    new_items = []
    since = request.GET.get("since") or ""
    if since.isdigit():
        new_items = [
            {"id": n.pk, "title": n.title, "link": n.link}
            for n in qs.filter(pk__gt=int(since)).order_by("pk")[:5]
        ]

    return JsonResponse({
        "authenticated": True,
        "unread": unread,
        "latest_id": latest_id,
        "new": new_items,
    })


@require_GET
@never_cache
def mini(request):
    """HTML fragment for the header notification dropdown (fetched on demand)."""
    items = []
    if request.user.is_authenticated:
        items = request.user.notifications.all()[:10]
    return render(request, "includes/notification_items.html", {"notifications": items})


@require_POST
def mark_read(request, pk):
    if not request.user.is_authenticated:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"authenticated": False}, status=401)
        return redirect("accounts:login")
    request.user.notifications.filter(pk=pk).update(is_read=True)
    unread = request.user.notifications.filter(is_read=False).count()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "unread": unread})
    return redirect(request.META.get("HTTP_REFERER", "/"))


@require_POST
def mark_all_read(request):
    if not request.user.is_authenticated:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"authenticated": False}, status=401)
        return redirect("accounts:login")
    request.user.notifications.update(is_read=True)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"ok": True, "unread": 0})
    messages.success(request, _("All notifications marked as read."))
    return redirect(request.META.get("HTTP_REFERER", "/"))


@require_POST
def subscribe(request):
    """Newsletter signup (homepage/footer form)."""
    if not throttle(f"newsletter:{client_ip(request)}", limit=5, period=300):
        return JsonResponse(
            {"ok": False, "message": _("Too many attempts — try again later.")},
            status=429,
        )
    email = (request.POST.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return JsonResponse(
            {"ok": False, "message": _("Please enter a valid email address.")},
            status=400,
        )
    obj, created = NewsletterSubscriber.objects.get_or_create(email=email)
    if not created and not obj.is_active:
        obj.is_active = True
        obj.save(update_fields=["is_active"])
    return JsonResponse({
        "ok": True,
        "message": _("You're subscribed! Watch your inbox for deals."),
    })
