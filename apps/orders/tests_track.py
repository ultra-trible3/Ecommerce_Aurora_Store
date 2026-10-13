"""Order tracking access: signed-in owner, staff, and email/phone checks."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.orders.models import Order, OrderItem

User = get_user_model()


class OrderTrackingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="trackme", email="trackme@example.com",
            password="s3cret-pass", role=User.Role.CUSTOMER,
        )
        cls.stranger = User.objects.create_user(
            username="nosy", email="nosy@example.com",
            password="s3cret-pass", role=User.Role.CUSTOMER,
        )
        cls.staff = User.objects.create_superuser(
            username="boss", email="boss@example.com", password="s3cret-pass"
        )
        cls.order = Order.objects.create(
            order_number="ORD-TRACK-0001",
            user=cls.owner,
            email=cls.owner.email,
            shipping_full_name="Track Me",
            shipping_phone="+15550100",
            shipping_address_line1="10 Main St",
            shipping_city="Springfield",
            shipping_postal_code="62704",
            subtotal=Decimal("49.00"),
            total=Decimal("49.00"),
        )
        cls.url = reverse("orders:track", args=[cls.order.order_number])

    def test_anonymous_gets_verification_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["needs_verification"])
        self.assertContains(response, 'name="email"')

    def test_anonymous_with_correct_email_is_verified(self):
        response = self.client.get(f"{self.url}?email=TRACKME@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context.get("needs_verification"))
        self.assertContains(response, "track-timeline")
        # Verification is remembered for later visits.
        response = self.client.get(self.url)
        self.assertFalse(response.context.get("needs_verification"))

    def test_anonymous_with_wrong_email_gets_error(self):
        response = self.client.get(f"{self.url}?email=wrong@example.com")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["needs_verification"])
        self.assertIn("does not match", response.context["error"])

    def test_anonymous_with_phone_is_verified(self):
        response = self.client.get(f"{self.url}?phone=%2B1%20(555)%200100")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context.get("needs_verification"))
        self.assertContains(response, "track-timeline")

    def test_signed_in_owner_tracks_without_credentials(self):
        """The plain /orders/track/<number>/ link works with a login session."""
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context.get("needs_verification"))
        self.assertContains(response, "track-timeline")
        self.assertNotContains(response, 'class="verify-form"')

    def test_signed_in_stranger_still_verifies(self):
        self.client.force_login(self.stranger)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["needs_verification"])

    def test_management_tracks_without_credentials(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context.get("needs_verification"))
        self.assertContains(response, "track-timeline")

    def test_unknown_order_is_404(self):
        response = self.client.get("/orders/track/ORD-DOES-NOT-EXIST/")
        self.assertEqual(response.status_code, 404)

    def test_verification_form_offers_sign_in_for_account_orders(self):
        response = self.client.get(self.url)
        self.assertContains(response, reverse("accounts:login"))
        self.assertContains(response, "Sign in to track")

    def test_order_list_has_track_button(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("orders:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.url)

    def test_order_detail_has_track_button(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("orders:detail", args=[self.order.order_number]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.url)


class OrderInvoicePdfTests(TestCase):
    """The downloadable invoice PDF uses the shared branded theme."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(
            username="invoicer", email="invoicer@example.com",
            password="s3cret-pass", role=User.Role.CUSTOMER,
        )
        cls.order = Order.objects.create(
            order_number="ORD-INVOICE-0001",
            user=cls.owner,
            email=cls.owner.email,
            shipping_full_name="Invoice Buyer",
            shipping_address_line1="10 Main St",
            shipping_city="Springfield",
            shipping_postal_code="62704",
            billing_full_name="Invoice Buyer",
            billing_address_line1="10 Main St",
            billing_city="Springfield",
            billing_postal_code="62704",
            subtotal=Decimal("49.00"),
            discount=Decimal("5.00"),
            shipping_cost=Decimal("4.00"),
            tax=Decimal("3.00"),
            total=Decimal("51.00"),
        )
        OrderItem.objects.create(
            order=cls.order,
            product_name="Aurora Hoodie",
            product_sku="AUR-HOOD-01",
            unit_price=Decimal("24.50"),
            quantity=2,
            line_total=Decimal("49.00"),
        )
        cls.url = reverse("orders:invoice_pdf", args=[cls.order.order_number])

    def test_invoice_pdf_downloads(self):
        self.client.force_login(self.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response["Content-Disposition"])
        content = b"".join(response.streaming_content)
        self.assertTrue(content.startswith(b"%PDF"))

    def test_invoice_pdf_renders_in_arabic(self):
        """Arabic invoices embed the bundled Amiri font like the reports."""
        self.client.force_login(self.owner)
        response = self.client.get(self.url, HTTP_ACCEPT_LANGUAGE="ar")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        content = b"".join(response.streaming_content)
        self.assertTrue(content.startswith(b"%PDF"))
        self.assertIn(b"Amiri", content)


class OrdersListUiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="listfan", email="listfan@example.com",
            password="s3cret-pass", role=User.Role.CUSTOMER,
        )
        cls.orders = {}
        for status in ("pending", "shipped", "delivered", "cancelled"):
            cls.orders[status] = Order.objects.create(
                order_number=f"ORD-LIST-{status.upper()}",
                user=cls.user,
                email=cls.user.email,
                status=status,
                shipping_full_name="List Fan",
                shipping_city="Springfield",
                shipping_address_line1="10 Main St",
                shipping_postal_code="62704",
                subtotal=Decimal("49.00"),
                total=Decimal("49.00"),
            )

    def test_progress_percent_tracks_fulfilment(self):
        expected = {
            "pending": 14,
            "shipped": 71,
            "delivered": 100,
            "cancelled": 100,
        }
        for status, percent in expected.items():
            with self.subTest(status=status):
                self.assertEqual(
                    self.orders[status].progress_percent, percent
                )

    def test_list_renders_filters_progress_and_actions(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("orders:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "au-chips")
        self.assertContains(response, "au-progress")
        for status, order in self.orders.items():
            self.assertContains(response, order.order_number)
            self.assertContains(
                response, reverse("orders:track", args=[order.order_number])
            )
            self.assertContains(
                response, reverse("orders:detail", args=[order.order_number])
            )
            self.assertContains(
                response, reverse("orders:invoice", args=[order.order_number])
            )

    def test_status_filter_narrows_the_list(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("orders:list") + "?status=shipped")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ORD-LIST-SHIPPED")
        self.assertNotContains(response, "ORD-LIST-PENDING")
