"""Promotions & content: coupons, review moderation and store settings."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy
from django.views.decorators.http import require_http_methods, require_POST

from apps.catalog.brand_logos import (
    MARQUEE_SETTING_KEY,
    get_brand_logos,
    serialize_brand_logos,
)
from apps.core.utils import paginate
from apps.coupons.models import Coupon
from apps.notifications.models import Setting
from apps.reviews.models import Review
from .decorators import management_required, permission_required
from .forms import CouponForm, ReviewReplyForm


# --------------------------------------------------------------------------
# Coupons
# --------------------------------------------------------------------------
@management_required
@permission_required("coupons.view_coupon")
def coupons(request):
    qs = Coupon.objects.order_by("-created_at")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(code__icontains=q)
    if request.GET.get("state") == "inactive":
        qs = qs.filter(is_active=False)

    page_obj = paginate(request, qs, per_page=20)
    rows = []
    for coupon in page_obj.object_list:
        rows.append({
            "obj": coupon,
            "redemptions": coupon.redemptions.count(),
        })
    return render(
        request,
        "management/coupons/list.html",
        {
            "nav": "coupons",
            "page_obj": page_obj,
            "rows": rows,
            "q": q,
        },
    )


@management_required
@permission_required("coupons.add_coupon")
@require_http_methods(["GET", "POST"])
def coupon_edit(request, pk=None):
    coupon = get_object_or_404(Coupon, pk=pk) if pk else None
    form = CouponForm(request.POST or None, instance=coupon)
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(
            request,
            _("Coupon %(code)s %(action)s.")
            % {
                "code": obj.code,
                "action": _("updated") if pk else _("created"),
            },
        )
        return redirect("dashboard:coupons")
    return render(
        request,
        "management/coupons/form.html",
        {
            "nav": "coupons",
            "form": form,
            "coupon": coupon,
            "mode": "edit" if pk else "create",
        },
    )


@management_required
@permission_required("coupons.delete_coupon")
@require_POST
def coupon_delete(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)
    code = coupon.code
    coupon.delete()
    messages.success(
        request, _("Coupon %(code)s deleted.") % {"code": code}
    )
    return redirect("dashboard:coupons")


# --------------------------------------------------------------------------
# Review moderation
# --------------------------------------------------------------------------
@management_required
@permission_required("reviews.view_review")
def reviews(request):
    status = request.GET.get("status")
    if status is None:
        status = Review.Status.PENDING
    qs = Review.objects.select_related("product", "user").order_by(
        "-created_at"
    )
    if status:
        qs = qs.filter(status=status)

    page_obj = paginate(request, qs, per_page=20)
    return render(
        request,
        "management/reviews.html",
        {
            "nav": "reviews",
            "page_obj": page_obj,
            "reviews": page_obj.object_list,
            "status_filter": status,
            "status_choices": Review.Status.choices,
            "pending_count": Review.objects.filter(
                status=Review.Status.PENDING
            ).count(),
        },
    )


@management_required
@permission_required("reviews.change_review")
@require_POST
def review_moderate(request, pk):
    review = get_object_or_404(Review, pk=pk)
    action = request.POST.get("action", "")
    if action == "approve":
        review.status = Review.Status.APPROVED
        review.save(update_fields=["status"])
        _refresh_rating(review.product)
        messages.success(request, _("Review approved."))
    elif action == "reject":
        review.status = Review.Status.REJECTED
        review.save(update_fields=["status"])
        _refresh_rating(review.product)
        messages.info(request, _("Review rejected."))
    elif action == "reply":
        form = ReviewReplyForm(request.POST)
        if form.is_valid():
            review.admin_reply = form.cleaned_data["admin_reply"]
            review.save(update_fields=["admin_reply"])
            review.status = Review.Status.APPROVED
            review.save(update_fields=["status"])
            _refresh_rating(review.product)
            messages.success(request, _("Reply published."))
    return redirect(_reviews_url(request.POST.get("next_status")))


def _reviews_url(status):
    from django.urls import reverse

    base = reverse("dashboard:reviews")
    return f"{base}?status={status}" if status else base


def _refresh_rating(product):
    from apps.reviews.services import refresh_product_rating

    try:
        refresh_product_rating(product)
    except Exception:  # pragma: no cover
        pass


# --------------------------------------------------------------------------
# Store settings
# --------------------------------------------------------------------------
DEFAULT_SETTINGS = [
    ("store_name", _lazy("Store name"), "general", _lazy("Shown in the header, emails and invoices.")),
    ("store_email", _lazy("Support email"), "general", _lazy("Reply-to address for customer emails.")),
    ("store_phone", _lazy("Support phone"), "general", _lazy("Displayed in the footer and emails.")),
    ("currency_symbol", _lazy("Currency symbol"), "commerce", _lazy("e.g. $, €, £")),
    ("low_stock_threshold", _lazy("Low stock threshold"), "inventory", _lazy("Notify staff at or below this stock level.")),
    ("orders_from_email", _lazy("Orders from address"), "commerce", _lazy("Sender for order confirmation emails.")),
    (
        MARQUEE_SETTING_KEY,
        _lazy("Logo marquee"),
        "content",
        _lazy("One logo per line: Name | images/brands/file.svg (path is relative to /static/). "
              "Leave empty to use the built-in list."),
    ),
]

# Settings that need a multi-line textarea instead of a single-line input.
TEXTAREA_SETTINGS = {MARQUEE_SETTING_KEY}


@management_required
@require_http_methods(["GET", "POST"])
@permission_required("notifications.change_setting")
def settings(request):
    if request.method == "POST":
        updated = 0
        for key, label, group, help_text in DEFAULT_SETTINGS:
            if key in request.POST:
                Setting.set(
                    key,
                    request.POST.get(key, "").strip(),
                    label=label,
                    group=group,
                    help_text=help_text,
                )
                updated += 1
        messages.success(
            request, _("%(count)s setting(s) saved.") % {"count": updated}
        )
        return redirect("dashboard:settings")

    values = {}
    for key, label, group, help_text in DEFAULT_SETTINGS:
        values[key] = Setting.get(key)
    # Prefill the marquee editor with the currently effective logos so saving
    # the form keeps them when the setting row does not exist yet.
    if not values[MARQUEE_SETTING_KEY]:
        values[MARQUEE_SETTING_KEY] = serialize_brand_logos(get_brand_logos())

    from django.conf import settings as dj_settings

    context = {
        "nav": "settings",
        "settings_rows": [
            {
                "key": key,
                "label": label,
                "group": group,
                "help_text": help_text,
                "value": values[key],
                "textarea": key in TEXTAREA_SETTINGS,
            }
            for key, label, group, help_text in DEFAULT_SETTINGS
        ],
        "env": {
            "stripe": bool(dj_settings.STRIPE_SECRET_KEY),
            "paypal": bool(dj_settings.PAYPAL_CLIENT_ID),
            "debug": dj_settings.DEBUG,
            "database": dj_settings.DATABASES["default"]["ENGINE"],
        },
    }
    return render(request, "management/settings.html", context)
