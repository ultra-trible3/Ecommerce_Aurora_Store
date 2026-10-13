"""Banner tracking and API views."""
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from apps.banners.models import Banner


@require_POST
@csrf_exempt
def track_impression(request, pk):
    """Track banner impression (called via 1x1 pixel or AJAX)."""
    banner = get_object_or_404(Banner, pk=pk, is_active=True)
    banner.record_impression()
    # Return 1x1 transparent GIF
    gif = (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff"
        b"\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00"
        b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02"
        b"\x02\x44\x01\x00\x3b"
    )
    return HttpResponse(gif, content_type="image/gif")


@require_POST
@csrf_exempt
def track_click(request, pk):
    """Track banner click (AJAX)."""
    banner = get_object_or_404(Banner, pk=pk, is_active=True)
    banner.record_click()
    return JsonResponse({"ok": True})


@require_POST
@csrf_exempt
def mark_seen(request, pk):
    """Mark banner as seen in current session (for show_once_per_session)."""
    banner = get_object_or_404(Banner, pk=pk)
    banner.mark_seen_in_session(request)
    return JsonResponse({"ok": True})