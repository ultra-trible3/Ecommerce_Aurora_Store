"""Payment gateway abstraction.

Providers implement a tiny interface; the rest of the codebase only talks to
``get_gateway()``.  Raw card data never touches our servers.
"""
import logging
from abc import ABC, abstractmethod

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


class GatewayError(Exception):
    """Payment provider error with a user-facing message."""


class BaseGateway(ABC):
    """Common payment provider contract."""

    code = "base"
    label = "Payment"

    @classmethod
    def is_configured(cls) -> bool:
        raise NotImplementedError

    @abstractmethod
    def create_payment(self, order, request=None):
        """Begin payment for an order. Returns a dict of provider data."""

    @abstractmethod
    def confirm_payment(self, order, payload=None):
        """Verify a payment server-side (webhook / capture / status check)."""

    @abstractmethod
    def refund(self, order, amount=None):
        """Refund a paid order (fully or partially)."""


class CashOnDeliveryGateway(BaseGateway):
    """Cash on delivery — no external provider required."""

    code = "cod"
    label = "Cash on delivery"

    @classmethod
    def is_configured(cls):
        return True

    def create_payment(self, order, request=None):
        return {
            "status": "pending",
            "message": "Pay with cash when your order arrives.",
            "requires_action": False,
        }

    def confirm_payment(self, order, payload=None):
        """COD is confirmed by staff on delivery (or by the customer)."""
        return {"status": "pending", "message": "Collect cash on delivery."}

    def refund(self, order, amount=None):
        return {"status": "refunded", "message": "Cash refund to be issued."}

    def cancel_payment(self, order, reason="Cancelled by system"):
        """Cancel a pending COD payment."""
        from apps.payments.models import Payment
        Payment.objects.filter(
            order=order, provider=self.code, status__in=[Payment.Status.PENDING, Payment.Status.PROCESSING]
        ).update(
            status=Payment.Status.CANCELLED,
            cancelled_at=timezone.now(),
            cancelled_reason=reason,
        )
        if order.payment_status in ["pending", "processing"]:
            order.payment_status = "cancelled"
            order.save(update_fields=["payment_status"])
        return {"status": "cancelled"}


class StripeGateway(BaseGateway):
    """Stripe via PaymentIntents — activated when API keys are provided."""

    code = "stripe"
    label = "Card (Stripe)"

    @classmethod
    def is_configured(cls):
        return bool(settings.STRIPE_SECRET_KEY)

    def _client(self):
        try:
            import stripe
        except ImportError as exc:  # pragma: no cover
            raise GatewayError("stripe package is not installed") from exc
        stripe.api_key = settings.STRIPE_SECRET_KEY
        return stripe

    def create_payment(self, order, request=None):
        stripe = self._client()
        try:
            intent = stripe.PaymentIntent.create(
                amount=int(order.total * 100),
                currency=settings.CURRENCY.lower(),
                metadata={
                    "order_number": order.order_number,
                    "customer_email": order.email,
                },
                automatic_payment_methods={"enabled": True},
            )
        except Exception as exc:  # pragma: no cover - needs live keys
            logger.error("Stripe PaymentIntent failed: %s", exc)
            raise GatewayError("Could not start the card payment.") from exc

        from apps.payments.models import Payment

        Payment.objects.update_or_create(
            order=order,
            provider=self.code,
            defaults={
                "transaction_id": intent.id,
                "client_secret": intent.client_secret,
                "status": Payment.Status.PROCESSING,
                "amount": order.total,
            },
        )
        order.payment_status = "processing"
        order.save(update_fields=["payment_status"])
        return {
            "client_secret": intent.client_secret,
            "payment_intent": intent.id,
            "requires_action": True,
            "status": "processing",
        }

    def confirm_payment(self, order, payload=None):
        """Called from the webhook — signature verified by the view."""
        stripe = self._client()
        from apps.payments.models import Payment

        payment = Payment.objects.filter(order=order, provider=self.code).first()
        intent_id = (payload or {}).get("payment_intent") or (
            payment.transaction_id if payment else ""
        )
        if not intent_id:
            raise GatewayError("Missing payment reference.")
        try:
            intent = stripe.PaymentIntent.retrieve(intent_id)
        except Exception as exc:  # pragma: no cover
            raise GatewayError("Could not verify the payment.") from exc

        if intent.status == "succeeded":
            if payment:
                payment.status = Payment.Status.PAID
                payment.webhook_received = True
                payment.provider_payload = {
                    "id": intent.id, "status": intent.status,
                }
                payment.save()
            return {"status": "paid"}
        return {"status": intent.status}

    def refund(self, order, amount=None):
        stripe = self._client()
        from apps.payments.models import Payment

        payment = Payment.objects.filter(
            order=order, provider=self.code, status=Payment.Status.PAID
        ).first()
        if payment is None:
            raise GatewayError("No captured payment to refund.")
        try:
            refund_obj = stripe.Refund.create(
                payment_intent=payment.transaction_id,
                amount=int((amount or order.total) * 100),
            )
        except Exception as exc:  # pragma: no cover
            raise GatewayError("Refund failed.") from exc
        payment.status = Payment.Status.REFUNDED
        payment.save(update_fields=["status"])
        return {"status": "refunded", "id": refund_obj.id}

    def cancel_payment(self, order, reason="Cancelled by system"):
        """Cancel a pending Stripe PaymentIntent."""
        from apps.payments.models import Payment
        import stripe
        
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        payment = Payment.objects.filter(
            order=order, provider=self.code, status__in=[Payment.Status.PENDING, Payment.Status.PROCESSING]
        ).first()
        
        if payment and payment.transaction_id:
            try:
                intent = stripe.PaymentIntent.retrieve(payment.transaction_id)
                if intent.status in ["requires_payment_method", "requires_confirmation", "requires_action"]:
                    stripe.PaymentIntent.cancel(payment.transaction_id)
            except stripe.error.StripeError:
                pass  # Ignore if already completed or cancelled
        
        Payment.objects.filter(
            order=order, provider=self.code, status__in=[Payment.Status.PENDING, Payment.Status.PROCESSING]
        ).update(
            status=Payment.Status.CANCELLED,
            cancelled_at=timezone.now(),
            cancelled_reason=reason,
        )
        
        if order.payment_status in ["pending", "processing"]:
            order.payment_status = "cancelled"
            order.save(update_fields=["payment_status"])
        
        return {"status": "cancelled"}

    def expire_payment(self, order, reason="Payment timed out"):
        """Mark a payment as expired (timeout)."""
        from apps.payments.models import Payment
        
        Payment.objects.filter(
            order=order, provider=self.code, status__in=[Payment.Status.PENDING, Payment.Status.PROCESSING]
        ).update(
            status=Payment.Status.EXPIRED,
            cancelled_at=timezone.now(),
            cancelled_reason=reason,
        )
        
        if order.payment_status in ["pending", "processing"]:
            order.payment_status = "cancelled"
            order.save(update_fields=["payment_status"])
        
        return {"status": "expired"}


class PayPalGateway(BaseGateway):
    """PayPal Checkout — activated when client id/secret are provided."""

    code = "paypal"
    label = "PayPal"

    API_BASE = {
        "sandbox": "https://api-m.sandbox.paypal.com",
        "live": "https://api-m.paypal.com",
    }

    @classmethod
    def is_configured(cls):
        return bool(settings.PAYPAL_CLIENT_ID and settings.PAYPAL_SECRET)

    def _base(self):
        return self.API_BASE.get(settings.PAYPAL_MODE, self.API_BASE["sandbox"])

    def _access_token(self):
        import requests

        try:
            resp = requests.post(
                f"{self._base()}/v1/oauth2/token",
                auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET),
                data={"grant_type": "client_credentials"},
                timeout=20,
            )
            resp.raise_for_status()
        except Exception as exc:  # pragma: no cover - needs live keys
            raise GatewayError("Could not reach PayPal.") from exc
        return resp.json()["access_token"]

    def create_payment(self, order, request=None):
        import requests

        token = self._access_token()
        return_url = request.build_absolute_uri(
            f"/payments/paypal/return/{order.order_number}/"
        ) if request else "/"
        cancel_url = request.build_absolute_uri(
            f"/payments/paypal/cancel/{order.order_number}/"
        ) if request else "/"
        try:
            resp = requests.post(
                f"{self._base()}/v2/checkout/orders",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "intent": "CAPTURE",
                    "purchase_units": [{
                        "reference_id": order.order_number,
                        "amount": {
                            "currency_code": settings.CURRENCY.upper(),
                            "value": f"{order.total:.2f}",
                        },
                    }],
                    "application_context": {
                        "return_url": return_url,
                        "cancel_url": cancel_url,
                    },
                },
                timeout=20,
            )
            resp.raise_for_status()
        except Exception as exc:  # pragma: no cover
            raise GatewayError("Could not start the PayPal payment.") from exc

        data = resp.json()
        approve = next(
            (l["href"] for l in data.get("links", [])
             if l.get("rel") == "approve"), ""
        )
        from apps.payments.models import Payment

        Payment.objects.filter(order=order, provider=self.code).update(
            transaction_id=data["id"],
            status=Payment.Status.PROCESSING,
        )
        return {
            "approve_url": approve,
            "paypal_order_id": data["id"],
            "requires_action": True,
            "status": "processing",
        }

    def confirm_payment(self, order, payload=None):
        """Capture the PayPal order server-side (called on return URL)."""
        import requests

        from apps.payments.models import Payment

        payment = Payment.objects.filter(order=order, provider=self.code).first()
        if payment is None or not payment.transaction_id:
            raise GatewayError("PayPal payment not found.")
        token = self._access_token()
        resp = requests.post(
            f"{self._base()}/v2/checkout/orders/"
            f"{payment.transaction_id}/capture",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=20,
        )
        if resp.status_code >= 400:  # pragma: no cover
            raise GatewayError("PayPal capture failed.")
        data = resp.json()
        if data.get("status") == "COMPLETED":
            payment.status = Payment.Status.PAID
            payment.webhook_received = True
            payment.provider_payload = data
            payment.save()
            return {"status": "paid"}
        return {"status": data.get("status", "unknown").lower()}

    def refund(self, order, amount=None):  # pragma: no cover - live keys
        raise GatewayError("PayPal refunds are processed from the dashboard.")

    def cancel_payment(self, order, reason="Cancelled by system"):
        """Cancel a pending PayPal order."""
        from apps.payments.models import Payment
        import requests
        
        payment = Payment.objects.filter(
            order=order, provider=self.code, status__in=[Payment.Status.PENDING, Payment.Status.PROCESSING]
        ).first()
        
        if payment and payment.transaction_id:
            try:
                token = self._access_token()
                requests.post(
                    f"{self._base()}/v2/checkout/orders/{payment.transaction_id}/cancel",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    timeout=10,
                )
            except Exception:
                pass  # Ignore if already completed
        
        Payment.objects.filter(
            order=order, provider=self.code, status__in=[Payment.Status.PENDING, Payment.Status.PROCESSING]
        ).update(
            status=Payment.Status.CANCELLED,
            cancelled_at=timezone.now(),
            cancelled_reason=reason,
        )
        
        if order.payment_status in ["pending", "processing"]:
            order.payment_status = "cancelled"
            order.save(update_fields=["payment_status"])
        
        return {"status": "cancelled"}

    def expire_payment(self, order, reason="Payment timed out"):
        """Mark a PayPal payment as expired."""
        from apps.payments.models import Payment
        
        Payment.objects.filter(
            order=order, provider=self.code, status__in=[Payment.Status.PENDING, Payment.Status.PROCESSING]
        ).update(
            status=Payment.Status.EXPIRED,
            cancelled_at=timezone.now(),
            cancelled_reason=reason,
        )
        
        if order.payment_status in ["pending", "processing"]:
            order.payment_status = "cancelled"
            order.save(update_fields=["payment_status"])
        
        return {"status": "expired"}


REGISTRY = {
    CashOnDeliveryGateway.code: CashOnDeliveryGateway,
    StripeGateway.code: StripeGateway,
    PayPalGateway.code: PayPalGateway,
}


def get_gateway(code):
    """Return an instantiated gateway for ``code`` (defaults to COD)."""
    gateway_cls = REGISTRY.get(code, CashOnDeliveryGateway)
    if not gateway_cls.is_configured():
        if code != CashOnDeliveryGateway.code:
            logger.warning("Gateway %s is not configured; falling back to COD.", code)
            gateway_cls = CashOnDeliveryGateway
    return gateway_cls()


def available_gateways():
    """Codes of the payment methods that can be offered at checkout."""
    codes = [CashOnDeliveryGateway.code]
    if StripeGateway.is_configured():
        codes.append(StripeGateway.code)
    if PayPalGateway.is_configured():
        codes.append(PayPalGateway.code)
    return codes
