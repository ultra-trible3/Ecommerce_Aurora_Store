"""Account views: registration, login, profile and addresses."""
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.cart.services import merge_guest_cart
from apps.core.utils import client_ip, safe_next, throttle
from apps.notifications.email import (
    send_verification_email,
    send_welcome_email,
)
from apps.orders.models import Order
from .models import Address
from .forms import (
    AddressForm,
    CustomPasswordChangeForm,
    CustomPasswordResetForm,
    LoginForm,
    ProfileForm,
    RegisterForm,
)

User = get_user_model()


# --------------------------------------------------------------------------
# Registration / authentication
# --------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if not throttle(f"register:{client_ip(request)}", limit=10, period=3600):
        messages.error(
            request, _("Too many sign-up attempts. Please try again later.")
        )
        return redirect("accounts:login")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                user.role = User.Role.CUSTOMER
                user.save(update_fields=["role"])
            send_verification_email(request, user)
            send_welcome_email(user)
            login(request, user)
            merge_guest_cart(request, user)
            messages.success(
                request,
                _("Your account is ready! We sent a confirmation email "
                  "(you can keep shopping right away)."),
            )
            return redirect(safe_next(request))
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    if not throttle(f"login:{client_ip(request)}", limit=20, period=300):
        messages.error(
            request, _("Too many login attempts. Please wait a few minutes.")
        )
        return redirect("accounts:login")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            if not user.is_active:
                messages.error(request, _("This account has been deactivated."))
                return redirect("accounts:login")
            login(request, user)
            if not form.cleaned_data.get("remember"):
                request.session.set_expiry(0)
            else:
                request.session.set_expiry(60 * 60 * 24 * 14)
            merge_guest_cart(request, user)
            next_url = safe_next(request, default="")
            if next_url:
                return redirect(next_url)
            messages.success(
                request,
                _("Welcome back, %(name)s!")
                % {"name": user.get_full_name() or user.email},
            )
            return redirect("/")
    else:
        form = LoginForm(request)

    return _render_login(request, form)


def _render_login(request, form):
    """Render the login page, showing a notice if this session was kicked.

    ``au_kicked`` is set by ``SingleDeviceSessionMiddleware`` when another
    device signs in; consume it once so the notice appears a single time.
    """
    kicked = bool(request.GET.get("kicked") or request.COOKIES.get("au_kicked"))
    response = render(
        request, "accounts/login.html", {"form": form, "kicked": kicked}
    )
    if request.COOKIES.get("au_kicked"):
        response.delete_cookie("au_kicked")
    return response


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, _("You have been signed out."))
    return redirect("accounts:login")


@require_http_methods(["GET"])
def verify_email(request):
    token = request.GET.get("token", "")
    # Never match an empty/None token: a blank value would otherwise match the
    # first user who has never verified (or has already verified).
    if not token:
        messages.error(request, _("That confirmation link is invalid or expired."))
        return redirect("accounts:login")
    user = User.objects.filter(verification_token=token).first()
    if user is None:
        messages.error(request, _("That confirmation link is invalid or expired."))
        return redirect("accounts:login")
    user.email_verified = True
    user.verification_token = None
    user.save(update_fields=["email_verified", "verification_token"])
    messages.success(request, _("Email confirmed — thank you!"))
    if not request.user.is_authenticated:
        login(request, user)
    return redirect("/")


@require_POST
def resend_verification(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    send_verification_email(request, request.user)
    messages.info(request, _("Confirmation email sent again."))
    return redirect("accounts:dashboard")


# --------------------------------------------------------------------------
# Account dashboard / profile
# --------------------------------------------------------------------------
@login_required
def dashboard(request):
    orders = (
        Order.objects.filter(user=request.user)
        .select_related()
        .order_by("-created_at")[:5]
    )
    stats = {
        "orders": Order.objects.filter(user=request.user).count(),
        "in_progress": Order.objects.filter(
            user=request.user,
            status__in=Order.ACTIVE_STATUSES,
        ).count(),
        "addresses": request.user.addresses.count(),
        "reviews": request.user.reviews.count(),
    }
    latest_notification = request.user.notifications.first()
    context = {
        "orders": orders,
        "stats": stats,
        "latest_notification": latest_notification,
    }
    return render(request, "accounts/dashboard.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user,
                           user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Profile updated."))
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user, user=request.user)
    return render(request, "accounts/profile.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def change_password(request):
    if request.method == "POST":
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            from django.contrib.auth import update_session_auth_hash

            update_session_auth_hash(request, user)
            messages.success(request, _("Password changed successfully."))
            return redirect("accounts:dashboard")
    else:
        form = CustomPasswordChangeForm(request.user)
    return render(request, "accounts/change_password.html", {"form": form})


# --------------------------------------------------------------------------
# Addresses
# --------------------------------------------------------------------------
@login_required
def addresses(request):
    qs = request.user.addresses.all()
    context = {
        "shipping": qs.filter(address_type="shipping"),
        "billing": qs.filter(address_type="billing"),
        "form": AddressForm(user=request.user),
    }
    return render(request, "accounts/addresses.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def address_create(request):
    if request.method == "POST":
        form = AddressForm(request.POST, user=request.user)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, _("Address added."))
            return redirect("accounts:addresses")
    else:
        form = AddressForm(user=request.user)
    return render(request, "accounts/address_form.html", {
        "form": form, "title": _("Add address"),
    })


@login_required
@require_http_methods(["GET", "POST"])
def address_update(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == "POST":
        form = AddressForm(request.POST, instance=address, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Address updated."))
            return redirect("accounts:addresses")
    else:
        form = AddressForm(instance=address, user=request.user)
    return render(request, "accounts/address_form.html", {
        "form": form, "title": _("Edit address"),
    })



@login_required
@require_POST
def address_delete(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.delete()
    messages.success(request, _("Address removed."))
    return redirect("accounts:addresses")


@login_required
@require_POST
def address_set_default(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.is_default = True
    address.save(update_fields=["is_default"])
    messages.success(request, _("Default address updated."))
    return redirect("accounts:addresses")

