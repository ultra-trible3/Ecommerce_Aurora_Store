"""Review views: create, edit, delete (with verified-purchase gating)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from apps.core.utils import client_ip, throttle
from apps.orders.models import Order, OrderItem
from .models import ProductAnswer, ProductQuestion, Review, ReviewImage
from .services import refresh_product_rating


def _has_purchased(user, product):
    """True when the user has a paid order containing this product."""
    return OrderItem.objects.filter(
        order__user=user,
        product=product,
        order__payment_status__in=["paid", "pending"],
        order__status__in=list(Order.ACTIVE_STATUSES) + [Order.Status.DELIVERED],
    ).exists()


@login_required
@require_POST
def create(request, slug):
    product = get_object_or_404(Product, slug=slug, status=Product.Status.ACTIVE)
    if Review.objects.filter(product=product, user=request.user).exists():
        messages.error(request, _("You have already reviewed this product."))
        return redirect(product.get_absolute_url() + "#reviews")

    rating = request.POST.get("rating", "5")
    body = (request.POST.get("body") or "").strip()
    title = (request.POST.get("title") or "").strip()[:200]
    try:
        rating = max(1, min(5, int(rating)))
    except (TypeError, ValueError):
        rating = 5
    if len(body) < 10:
        messages.error(request, _("Please write at least 10 characters."))
        return redirect(product.get_absolute_url() + "#reviews")

    review = Review.objects.create(
        product=product,
        user=request.user,
        rating=rating,
        title=title,
        body=body,
        is_verified_purchase=_has_purchased(request.user, product),
        status=Review.Status.PENDING,
    )
    for image in request.FILES.getlist("images"):
        if len(ReviewImage.objects.filter(review=review)) >= 4:
            break
        ReviewImage.objects.create(review=review, image=image)

    refresh_product_rating(product)
    messages.success(
        request,
        _("Thanks! Your review has been submitted and is awaiting moderation.")
        if review.status == Review.Status.PENDING
        else _("Review published."),
    )
    return redirect(product.get_absolute_url() + "#reviews")


@login_required
@require_POST
def edit(request, pk):
    review = get_object_or_404(Review, pk=pk, user=request.user)
    rating = request.POST.get("rating", review.rating)
    body = (request.POST.get("body") or review.body).strip()
    try:
        review.rating = max(1, min(5, int(rating)))
    except (TypeError, ValueError):
        pass
    if len(body) >= 10:
        review.body = body
        review.title = (request.POST.get("title") or review.title).strip()[:200]
        review.status = Review.Status.PENDING  # re-moderated after edit
        review.save()
        refresh_product_rating(review.product)
        messages.success(request, _("Review updated — it will be re-published shortly."))
    else:
        messages.error(request, _("Review text must be at least 10 characters."))
    return redirect(review.product.get_absolute_url() + "#reviews")


@login_required
@require_POST
def delete(request, pk):
    review = get_object_or_404(Review, pk=pk)
    if review.user_id != request.user.pk and not request.user.is_management:
        raise PermissionDenied(_("Not your review."))
    product = review.product
    review.delete()
    refresh_product_rating(product)
    messages.success(request, _("Review deleted."))
    if request.user.is_management:
        return redirect("dashboard:reviews_pending")
    return redirect(product.get_absolute_url() + "#reviews")


# --------------------------------------------------------------------------
# Product Q&A
# --------------------------------------------------------------------------
@require_POST
def ask_question(request, slug):
    """Accept a product question (guest-friendly) for moderation."""
    product = get_object_or_404(Product, slug=slug, status=Product.Status.ACTIVE)
    target = product.get_absolute_url() + "#questions"

    if not throttle(f"qa:{client_ip(request)}", limit=10, period=600):
        messages.error(request, _("You're asking too fast — please wait a moment."))
        return redirect(target)

    body = (request.POST.get("question") or request.POST.get("body") or "").strip()
    if len(body) < 5:
        messages.error(request, _("Please write at least 5 characters."))
        return redirect(target)

    user = request.user if request.user.is_authenticated else None
    asker_name = (request.POST.get("name") or "").strip()[:150]
    asker_email = (request.POST.get("email") or "").strip().lower()
    if user is None:
        from django.core.exceptions import ValidationError
        from django.core.validators import validate_email

        try:
            validate_email(asker_email)
        except ValidationError:
            messages.error(
                request, _("Please add a valid email so we can notify you of the answer.")
            )
            return redirect(target)

    ProductQuestion.objects.create(
        product=product,
        user=user,
        asker_name=asker_name,
        asker_email=asker_email,
        body=body,
    )
    messages.success(
        request, _("Thanks! Your question was submitted and is awaiting an answer.")
    )
    return redirect(target)
