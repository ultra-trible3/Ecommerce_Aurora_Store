"""Every email template must render without template errors."""
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase

from apps.catalog.models import Brand, Category, Product
from apps.orders.models import Order
from apps.accounts.models import User


class EmailTemplateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.request = RequestFactory().get("/")
        cls.category = Category.objects.create(name="Gear")
        cls.brand = Brand.objects.create(name="Aurora")
        cls.user = User.objects.create_user(
            username="ana", email="ana@example.com", password="pw"
        )
        cls.product = Product.objects.create(
            name="Trail Backpack", sku="BAG-001", category=cls.category,
            brand=cls.brand, price=49, stock_quantity=1, min_stock_level=2,
        )
        cls.order = Order.objects.create(
            order_number="ORD-20260101-0001", user=cls.user,
            email=cls.user.email, shipping_full_name="Ana",
            shipping_address_line1="10 Main St", shipping_city="Springfield",
            shipping_postal_code="62704", subtotal=49, total=49,
        )

    def _render(self, name, context):
        return render_to_string(name, context, request=self.request)

    def test_order_emails(self):
        for suffix in ("confirmation", "paid", "processing", "shipped",
                       "delivered", "cancelled", "refunded"):
            for ext in ("html", "txt"):
                with self.subTest(template=f"{suffix}.{ext}"):
                    out = self._render(f"emails/order_{suffix}.{ext}",
                                       {"order": self.order})
                    self.assertIn("ORD-20260101-0001", out)

    def test_transactional_emails(self):
        self.assertIn("ana", self._render(
            "emails/welcome.html", {"user": self.user}))
        self.assertIn("Confirm", self._render(
            "emails/verify_email.html", {"link": "http://x.test/confirm/"}))
        self.assertIn("Trail Backpack", self._render(
            "emails/low_stock.html", {"product": self.product}))
        out = self._render("emails/password_reset.html", {
            "protocol": "http", "domain": "test.local",
            "user": self.user, "uid": "uid", "token": "token",
        })
        self.assertIn("reset", out.lower())
        subject = self._render("emails/password_reset_subject.txt", {
            "site_name": "Aurora Store", "user": self.user,
            "uid": "uid", "token": "token",
        })
        self.assertIn("Aurora Store", subject)

    def test_email_uses_relative_and_absolute_urls(self):
        html = self._render("emails/order_confirmation.html",
                            {"order": self.order})
        self.assertIn("http://localhost:8000/orders/ORD-20260101-0001/", html)
