"""Refund service — server-side refund processing for payments."""
import logging
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .gateways import get_gateway
from .models import Payment
from apps.orders.models import Order

logger = logging.getLogger(__name__)


class RefundError(Exception):
    """User-facing refund error."""
    pass


class RefundService:
    """Process refunds for paid orders via their payment gateway."""

    @staticmethod
    def refund_order(order, amount=None, reason="", actor=None):
        """
        Refund a paid order (full or partial).

        Args:
            order: The Order instance
            amount: Decimal amount to refund (None = full order total)
            reason: Reason for refund (logged/stored)
            actor: User initiating the refund

        Returns:
            dict: {"status": "refunded" | "partial" | "failed", "details": ...}
        """
        if not order.is_paid:
            raise RefundError(_("Cannot refund an unpaid order."))

        payment = order.payments.filter(
            provider__in=["stripe", "paypal", "cod"],
            status=Payment.Status.PAID
        ).first()

        if not payment:
            raise RefundError(_("No captured payment found to refund."))

        refund_amount = Decimal(str(amount)) if amount is not None else order.total
        if refund_amount > order.total:
            raise RefundError(_("Refund amount cannot exceed order total."))

        gateway = get_gateway(payment.provider)
        try:
            result = gateway.refund(order, amount=refund_amount)
        except Exception as exc:
            logger.error("Refund failed for order %s: %s", order.order_number, exc)
            raise RefundError(str(exc))

        # Update payment record
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status"])

        # Update order payment status if fully refunded
        if refund_amount >= order.total:
            order.payment_status = "refunded"
            order.save(update_fields=["payment_status"])
            status = "refunded"
        else:
            status = "partial"

        logger.info(
            "Refund %s for order %s: %.2f %s (reason: %s, actor: %s)",
            status, order.order_number, refund_amount, settings.CURRENCY, reason, actor
        )

        return {
            "status": status,
            "amount": refund_amount,
            "provider_result": result,
        }

    @staticmethod
    def can_refund(order):
        """Check if order is eligible for refund."""
        if not order.is_paid:
            return False, _("Order is not paid.")
        if order.status in (Order.Status.REFUNDED, Order.Status.CANCELLED):
            return False, _("Order already refunded or cancelled.")
        payment = order.payments.filter(
            provider__in=["stripe", "paypal", "cod"],
            status=Payment.Status.PAID
        ).first()
        if not payment:
            return False, _("No captured payment found.")
        return True, ""