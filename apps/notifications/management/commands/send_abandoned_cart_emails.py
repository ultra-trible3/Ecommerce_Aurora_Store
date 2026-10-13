"""Management command to send abandoned cart recovery emails."""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.cart.models import Cart
from apps.notifications.email import send_email
from apps.notifications.models import AbandonedCart


class Command(BaseCommand):
    help = "Detect abandoned carts and send recovery emails."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=2,
            help="Hours of inactivity before a cart is considered abandoned (default: 2)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=100,
            help="Max emails to send per run (default: 100)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be done without sending emails",
        )

    def handle(self, *args, **options):
        hours = options["hours"]
        limit = options["limit"]
        dry_run = options["dry_run"]

        cutoff = timezone.now() - timedelta(hours=hours)

        # Find carts that haven't been updated in X hours, have items, and aren't recovered
        abandoned_carts = Cart.objects.filter(
            updated_at__lt=cutoff,
            items__isnull=False,
        ).exclude(
            items__isnull=True
        ).distinct()[:limit]

        self.stdout.write(f"Found {abandoned_carts.count()} candidate carts (inactive > {hours}h)")

        sent = 0
        skipped = 0

        for cart in abandoned_carts:
            email = cart.user.email if cart.user else None
            if not email:
                # Try to get email from session (guest checkout)
                from django.contrib.sessions.models import Session
                try:
                    session = Session.objects.get(session_key=cart.session_key)
                    data = session.get_decoded()
                    email = data.get("guest_email") or data.get("checkout_email")
                except Session.DoesNotExist:
                    pass

            if not email:
                skipped += 1
                continue

            # Check if we already sent recovery email for this cart
            existing = AbandonedCart.objects.filter(
                session_key=cart.session_key,
                user=cart.user,
                recovery_email_sent=True,
            ).first()
            if existing:
                skipped += 1
                continue

            # Build items snapshot
            items = []
            for item in cart.items.select_related("product", "variant"):
                if item.is_available:
                    items.append({
                        "name": item.display_name,
                        "quantity": item.quantity,
                        "price": float(item.unit_price),
                    })

            if not items:
                skipped += 1
                continue

            subtotal = float(cart.subtotal)
            recovery_url = settings.SITE_URL + "/checkout/"

            # Create abandoned cart record
            abandoned = AbandonedCart.objects.create(
                user=cart.user,
                session_key=cart.session_key,
                email=email,
                cart_data={"items": items},
                subtotal=subtotal,
                items_count=len(items),
            )

            if dry_run:
                self.stdout.write(f"  [DRY RUN] Would send to {email} (cart: {cart.id}, items: {len(items)}, subtotal: {subtotal})")
                abandoned.delete()
                continue

            # Send email
            sent_ok = send_email(
                f"You left something in your cart – {settings.SITE_NAME}",
                email,
                "abandoned_cart",
                {
                    "email": email,
                    "items": items,
                    "subtotal": subtotal,
                    "recovery_url": recovery_url,
                },
            )

            if sent_ok:
                abandoned.recovery_email_sent = True
                abandoned.recovery_email_sent_at = timezone.now()
                abandoned.save(update_fields=["recovery_email_sent", "recovery_email_sent_at"])
                sent += 1
                self.stdout.write(f"  ✓ Sent to {email} (cart: {cart.id})")
            else:
                abandoned.delete()
                skipped += 1
                self.stdout.write(f"  ✗ Failed to send to {email}")

        self.stdout.write(self.style.SUCCESS(f"Done. Sent: {sent}, Skipped: {skipped}"))