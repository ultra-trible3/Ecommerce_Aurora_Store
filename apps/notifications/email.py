"""Reusable email service built on Django's email framework."""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


def send_email(subject, to, template, context=None, from_email=None):
    """Render ``templates/emails/<template>.txt/html`` and send."""
    context = context or {}
    context.update({
        "SITE_NAME": settings.SITE_NAME,
        "SITE_TAGLINE": settings.SITE_TAGLINE,
        "SUPPORT_EMAIL": settings.SUPPORT_EMAIL,
        "SUPPORT_PHONE": settings.SUPPORT_PHONE,
        "CURRENCY_SYMBOL": settings.CURRENCY_SYMBOL,
        "SITE_URL": settings.SITE_URL,
    })
    to = [to] if isinstance(to, str) else list(to)
    if not to:
        return False
    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    try:
        text_body = render_to_string(f"emails/{template}.txt", context)
    except Exception:
        text_body = ""
    try:
        html_body = render_to_string(f"emails/{template}.html", context)
    except Exception as exc:  # pragma: no cover
        logger.warning("Missing email template %s: %s", template, exc)
        html_body = None

    message = EmailMultiAlternatives(subject, text_body, from_email, to)
    if html_body:
        message.attach_alternative(html_body, "text/html")
    try:
        message.send(fail_silently=False)
        return True
    except Exception as exc:  # pragma: no cover - logged, never breaks flow
        logger.error("Failed to send %s to %s: %s", template, to, exc)
        return False


# --------------------------------------------------------------------------
# Transactional helpers
# --------------------------------------------------------------------------
def send_verification_email(request, user):
    """Build an absolute verification link from the current request."""
    token = user.generate_verification_token()
    user.save(update_fields=["verification_token", "email_verification_sent_at"])
    link = request.build_absolute_uri(
        f"/accounts/verify/?token={token}"
    )
    return send_email(
        _("Confirm your %(site_name)s account") % {"site_name": settings.SITE_NAME},
        user.email,
        "verify_email",
        {"user": user, "token": token, "link": link},
    )


def send_welcome_email(user):
    return send_email(
        _("Welcome to %(site_name)s 🎉") % {"site_name": settings.SITE_NAME},
        user.email,
        "welcome",
        {"user": user},
    )


def send_order_email(order, kind):
    subjects = {
        "confirmation": _("Order %(number)s received")
        % {"number": order.order_number},
        "paid": _("Payment received for %(number)s") % {"number": order.order_number},
        "processing": _("Your order %(number)s is being prepared")
        % {"number": order.order_number},
        "shipped": _("Your order %(number)s has shipped")
        % {"number": order.order_number},
        "delivered": _("Your order %(number)s was delivered")
        % {"number": order.order_number},
        "cancelled": _("Your order %(number)s was cancelled")
        % {"number": order.order_number},
        "refunded": _("Refund processed for %(number)s")
        % {"number": order.order_number},
    }
    return send_email(
        subjects.get(kind, _("Update for %(number)s") % {"number": order.order_number}),
        order.email,
        f"order_{kind}",
        {"order": order, "items": order.items.all()},
    )


def send_low_stock_email(product, threshold):
    return send_email(
        _("Low stock alert: %(product)s") % {"product": product.name},
        settings.SUPPORT_EMAIL,
        "low_stock",
        {"product": product, "threshold": threshold},
    )
