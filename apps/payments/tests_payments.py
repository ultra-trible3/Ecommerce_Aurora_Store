"""Cash on delivery + Stripe payment flows."""
import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import Category, Product
from apps.orders.models import Order, ShippingMethod
from apps.payments.models import Payment

User = get_user_model()

CHECKOUT_FIELDS = {
    "email": "buyer@example.com",
    "full_name": "Bud Buyer",
    "phone": "+1 (555) 333-4444",
    "address_line1": "99 Market St",
    "city": "Portland",
    "state": "OR",
    "postal_code": "97201",
    "country": "United States",
    "same_as_shipping": "on",
    "shipping_method": "standard",
}


class PaymentFlowTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="Gear")
        self.product = Product.objects.create(
            name="Trail Backpack", sku="BAG-001", category=category,
            price=Decimal("40.00"), stock_quantity=10,
        )
        ShippingMethod.objects.create(
            name="Standard shipping", code="standard", cost=Decimal("5.00"),
        )
        self.user = User.objects.create_user(
            username="bud", email="buyer@example.com", password="whatever123",
        )
        self.client.force_login(self.user)

    def _add_to_cart(self):
        self.client.post(reverse("cart:add"), {
            "product": self.product.pk, "quantity": 2,
        })

    def _place(self, **extra):
        data = {**CHECKOUT_FIELDS, "payment_method": "cod", **extra}
        return self.client.post(reverse("checkout:place"), data)

    # ------------------------------------------------------------------ COD
    def test_cod_checkout_creates_pending_payment(self):
        self._add_to_cart()
        response = self._place()
        self.assertEqual(response.status_code, 302)

        order = Order.objects.get()
        self.assertEqual(order.payment_method, "cod")
        self.assertEqual(order.payment_status, "pending")
        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.provider, "cod")
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_cod_marked_paid_on_delivery(self):
        self._add_to_cart()
        self._place()
        order = Order.objects.get()

        from apps.orders.services import transition_status

        transition_status(order, Order.Status.DELIVERED, note="Handed over")
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertIsNotNone(order.delivered_at)
        self.assertEqual(
            Payment.objects.get(order=order).status, Payment.Status.PAID
        )

    def test_cod_marked_paid_from_staff_portal(self):
        self._add_to_cart()
        self._place()
        order = Order.objects.get()

        staff = User.objects.create_user(
            username="omar", email="orders@example.com", password="s3cret-pass",
            role=User.Role.STAFF, is_staff=True, is_superuser=True,
        )
        self.client.force_login(staff)
        self.client.post(
            reverse("dashboard:order_payment", args=[order.order_number]),
            {"action": "mark_paid"},
        )
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(
            Payment.objects.get(order=order, provider="cod").status,
            Payment.Status.PAID,
        )

    # ------------------------------------------------- Stripe availability
    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLIC_KEY="")
    def test_stripe_option_hidden_without_keys(self):
        self._add_to_cart()
        response = self.client.get(reverse("checkout:start"))
        self.assertNotContains(response, 'value="stripe"')

    @override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLIC_KEY="")
    def test_unconfigured_stripe_rejected_server_side(self):
        self._add_to_cart()
        response = self._place(payment_method="stripe")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_123", STRIPE_PUBLIC_KEY="pk_test_123"
    )
    def test_stripe_option_shown_when_configured(self):
        self._add_to_cart()
        response = self.client.get(reverse("checkout:start"))
        self.assertContains(response, 'value="stripe"')

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_123", STRIPE_PUBLIC_KEY="pk_test_123"
    )
    def test_each_payment_option_shows_its_own_description(self):
        # Django 5 BoundWidget has no `choice_value` — a silent template
        # miss would show the PayPal blurb for every method.
        self._add_to_cart()
        html = self.client.get(reverse("checkout:start")).content.decode()
        self.assertIn("Pay the courier when your order arrives.", html)
        self.assertIn("Encrypted card payment", html)
        # Shipping rows must resolve their price (same radio.data.value bug).
        self.assertIn("$5.00", html)

    # ------------------------------------------------------- Stripe payment
    def _place_stripe(self):
        self._add_to_cart()
        with patch(
            "apps.payments.gateways.StripeGateway.create_payment",
            return_value={
                "client_secret": "pi_secret_123",
                "payment_intent": "pi_123",
                "requires_action": True,
                "status": "processing",
            },
        ) as mocked:
            response = self._place(payment_method="stripe")
        return response, mocked

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_123", STRIPE_PUBLIC_KEY="pk_test_123"
    )
    def test_stripe_checkout_redirects_to_card_page(self):
        response, _ = self._place_stripe()
        order = Order.objects.get()
        self.assertRedirects(
            response,
            reverse("payments:stripe_pay", args=[order.order_number]),
            fetch_redirect_response=False,
        )
        self.assertEqual(order.payment_method, "stripe")
        self.assertEqual(order.payment_status, "pending")

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_123", STRIPE_PUBLIC_KEY="pk_test_123"
    )
    def test_card_page_renders_for_owner(self):
        self.client.force_login(self.user)
        with patch(
            "apps.payments.gateways.StripeGateway.create_payment",
            return_value={
                "client_secret": "pi_secret_123",
                "payment_intent": "pi_123",
                "requires_action": True,
                "status": "processing",
            },
        ):
            self._place_stripe()
            order = Order.objects.get()
            page = self.client.get(
                reverse("payments:stripe_pay", args=[order.order_number])
            )
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "pi_secret_123")
        self.assertContains(page, "pk_test_123")

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_123", STRIPE_PUBLIC_KEY="pk_test_123"
    )
    def test_confirm_marks_order_paid(self):
        self.client.force_login(self.user)
        self._place_stripe()
        order = Order.objects.get()

        intent = SimpleNamespace(id="pi_123", status="succeeded")
        with patch("stripe.PaymentIntent.retrieve", return_value=intent):
            response = self.client.post(
                reverse("payments:stripe_confirm", args=[order.order_number]),
                data=json.dumps({"payment_intent": "pi_123", "status": "succeeded"}),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertEqual(
            Payment.objects.get(order=order, provider="stripe").status,
            Payment.Status.PAID,
        )

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_123", STRIPE_PUBLIC_KEY="pk_test_123"
    )
    def test_authenticated_stripe_payment_lands_on_tracking(self):
        # Authenticated user places a Stripe order…
        self._place_stripe()
        order = Order.objects.get()

        # …opens the card page with the checkout session…
        with patch(
            "apps.payments.gateways.StripeGateway.create_payment",
            return_value={
                "client_secret": "pi_secret_123",
                "payment_intent": "pi_123",
                "requires_action": True,
                "status": "processing",
            },
        ):
            page = self.client.get(
                reverse("payments:stripe_pay", args=[order.order_number])
            )
        self.assertEqual(page.status_code, 200)

        # …and after confirming, is sent to the order detail page (not track page).
        intent = SimpleNamespace(id="pi_123", status="succeeded")
        with patch("stripe.PaymentIntent.retrieve", return_value=intent):
            confirm = self.client.post(
                reverse("payments:stripe_confirm", args=[order.order_number]),
                data=json.dumps({"payment_intent": "pi_123"}),
                content_type="application/json",
            )
        self.assertEqual(
            confirm.json()["redirect"], f"/orders/{order.order_number}/"
        )
        detail = self.client.get(confirm.json()["redirect"])
        self.assertEqual(detail.status_code, 200)

    @override_settings(
        STRIPE_SECRET_KEY="sk_test_123", STRIPE_PUBLIC_KEY="pk_test_123"
    )
    def test_order_detail_offers_pay_now_for_unpaid_stripe(self):
        self.client.force_login(self.user)
        self._place_stripe()
        order = Order.objects.get()
        detail = self.client.get(
            reverse("orders:detail", args=[order.order_number])
        )
        self.assertContains(
            detail, reverse("payments:stripe_pay", args=[order.order_number])
        )
        self.assertContains(detail, "Pay now")
