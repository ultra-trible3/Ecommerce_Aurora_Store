"""Management command to clean up expired/abandoned payments."""
import logging
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.services import transition_status
from apps.payments.gateways import get_gateway
from apps.payments.models import Payment

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Clean up expired/abandoned payments and update order statuses"

    def add_arguments(self, parser):
        parser.add_argument(
            "--stripe-timeout",
            type=int,
            default=30,
            help="Minutes after which a Stripe PaymentIntent is considered abandoned (default: 30)",
        )
        parser.add_argument(
            "--paypal-timeout",
            type=int,
            default=30,
            help="Minutes after which a PayPal order is considered abandoned (default: 30)",
        )
        parser.add_argument(
            "--cod-timeout",
            type=int,
            default=60,
            help="Minutes after which an unconfirmed COD order is auto-cancelled (default: 60)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )

    def handle(self, *args, **options):
        stripe_timeout = options["stripe_timeout"]
        paypal_timeout = options["paypal_timeout"]
        cod_timeout = options["cod_timeout"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        now = timezone.now()

        # 1. Expire abandoned Stripe payments
        stripe_cutoff = now - timedelta(minutes=stripe_timeout)
        expired_stripe = Payment.objects.filter(
            provider="stripe",
            status__in=[Payment.Status.PENDING, Payment.Status.PROCESSING],
            created_at__lt=stripe_cutoff,
        ).select_related("order")

        self.stdout.write(f"Found {expired_stripe.count()} expired Stripe payments")
        
        for payment in expired_stripe:
            order = payment.order
            if dry_run:
                self.stdout.write(f"  Would expire: {order.order_number} (PaymentIntent: {payment.transaction_id})")
                continue
            
            try:
                gateway = get_gateway("stripe")
                gateway.expire_payment(order, reason=f"Stripe PaymentIntent abandoned after {stripe_timeout} minutes")
                logger.info("Expired Stripe payment for order %s", order.order_number)
                self.stdout.write(f"  Expired: {order.order_number}")
            except Exception as exc:
                logger.error("Failed to expire Stripe payment for order %s: %s", order.order_number, exc)
                self.stdout.write(self.style.ERROR(f"  Error expiring {order.order_number}: {exc}"))

        # 2. Expire abandoned PayPal payments
        paypal_cutoff = now - timedelta(minutes=paypal_timeout)
        expired_paypal = Payment.objects.filter(
            provider="paypal",
            status__in=[Payment.Status.PENDING, Payment.Status.PROCESSING],
            created_at__lt=paypal_cutoff,
        ).select_related("order")

        self.stdout.write(f"Found {expired_paypal.count()} expired PayPal payments")
        
        for payment in expired_paypal:
            order = payment.order
            if dry_run:
                self.stdout.write(f"  Would expire: {order.order_number} (PayPal Order: {payment.transaction_id})")
                continue
            
            try:
                gateway = get_gateway("paypal")
                gateway.expire_payment(order, reason=f"PayPal order abandoned after {paypal_timeout} minutes")
                logger.info("Expired PayPal payment for order %s", order.order_number)
                self.stdout.write(f"  Expired: {order.order_number}")
            except Exception as exc:
                logger.error("Failed to expire PayPal payment for order %s: %s", order.order_number, exc)
                self.stdout.write(self.style.ERROR(f"  Error expiring {order.order_number}: {exc}"))

        # 3. Auto-cancel unconfirmed COD orders
        cod_cutoff = now - timedelta(minutes=cod_timeout)
        # COD orders that are still PENDING (not confirmed) after timeout
        expired_cod_orders = Order.objects.filter(
            payment_method="cod",
            status=Order.Status.PENDING,
            created_at__lt=cod_cutoff,
        )

        self.stdout.write(f"Found {expired_cod_orders.count()} unconfirmed COD orders past timeout")
        
        for order in expired_cod_orders:
            if dry_run:
                self.stdout.write(f"  Would cancel: {order.order_number} (COD, unconfirmed after {cod_timeout} min)")
                continue
            
            try:
                # Cancel the COD payment
                gateway = get_gateway("cod")
                gateway.cancel_payment(order, reason=f"COD order not confirmed after {cod_timeout} minutes")
                
                # Cancel the order
                transition_status(
                    order, Order.Status.CANCELLED,
                    note=f"COD order auto-cancelled after {cod_timeout} minutes without confirmation"
                )
                
                logger.info("Auto-cancelled COD order %s", order.order_number)
                self.stdout.write(f"  Cancelled: {order.order_number}")
            except Exception as exc:
                logger.error("Failed to auto-cancel COD order %s: %s", order.order_number, exc)
                self.stdout.write(self.style.ERROR(f"  Error cancelling {order.order_number}: {exc}"))

        # Summary
        total_cleaned = expired_stripe.count() + expired_paypal.count() + expired_cod_orders.count()
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"\nDRY RUN: Would process {total_cleaned} items"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nProcessed {total_cleaned} expired/abandoned items"))