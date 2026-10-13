"""Banner management views for the dashboard."""
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.utils import paginate
from apps.banners.forms import BannerForm
from apps.banners.models import Banner
from .decorators import management_required, permission_required


@management_required
@permission_required("banners.view_banner")
def banners(request):
    """List all banners with filtering."""
    qs = Banner.objects.all()

    # Filters
    state = request.GET.get("state", "")
    if state == "active":
        qs = qs.filter(is_active=True)
    elif state == "inactive":
        qs = qs.filter(is_active=False)
    elif state == "expired":
        from django.utils import timezone
        qs = qs.filter(valid_until__lt=timezone.now())
    elif state == "scheduled":
        from django.utils import timezone
        qs = qs.filter(valid_from__gt=timezone.now())

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(models.Q(title__icontains=q) | models.Q(slug__icontains=q))

    device = request.GET.get("device", "")
    if device:
        qs = qs.filter(device_target=device)

    page_obj = paginate(request, qs, per_page=20)
    context = {
        "nav": "banners",
        "page_obj": page_obj,
        "banners": page_obj.object_list,
        "q": q,
        "state_filter": state,
        "device_filter": device,
        "device_choices": Banner.DeviceTarget.choices,
        "state_choices": [
            ("", _("All")),
            ("active", _("Active")),
            ("inactive", _("Inactive")),
            ("expired", _("Expired")),
            ("scheduled", _("Scheduled")),
        ],
    }
    return render(request, "management/banners/list.html", context)


@management_required
@permission_required("banners.add_banner")
@require_http_methods(["GET", "POST"])
def banner_create(request):
    """Create a new banner."""
    form = BannerForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        banner = form.save()
        messages.success(
            request,
            _("Banner '%(title)s' created.") % {"title": banner.title},
        )
        return redirect("dashboard:banners")
    return render(
        request,
        "management/banners/form.html",
        {
            "nav": "banners",
            "form": form,
            "mode": "create",
        },
    )


@management_required
@permission_required("banners.change_banner")
@require_http_methods(["GET", "POST"])
def banner_edit(request, pk):
    """Edit an existing banner."""
    banner = get_object_or_404(Banner, pk=pk)
    form = BannerForm(request.POST or None, request.FILES or None, instance=banner)
    if request.method == "POST" and form.is_valid():
        banner = form.save()
        messages.success(
            request,
            _("Banner '%(title)s' updated.") % {"title": banner.title},
        )
        return redirect("dashboard:banners")
    return render(
        request,
        "management/banners/form.html",
        {
            "nav": "banners",
            "form": form,
            "banner": banner,
            "mode": "edit",
        },
    )


@management_required
@permission_required("banners.delete_banner")
@require_POST
def banner_delete(request, pk):
    """Delete a banner."""
    banner = get_object_or_404(Banner, pk=pk)
    title = banner.title
    banner.delete()
    messages.success(
        request, _("Banner '%(title)s' deleted.") % {"title": title}
    )
    return redirect("dashboard:banners")


@management_required
@permission_required("banners.view_banner")
def banner_preview(request, pk):
    """Preview a banner (AJAX)."""
    banner = get_object_or_404(Banner, pk=pk)
    # Render the banner template with mock request context
    from django.template.loader import render_to_string

    html = render_to_string(
        "includes/hero_banner.html",
        {"banner": banner, "preview": True},
        request=request,
    )
    return JsonResponse({"html": html, "click_action": banner.click_action})


import django.db.models as models