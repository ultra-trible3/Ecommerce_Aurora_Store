"""End-to-end smoke tests covering the storefront, cart and checkout."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart
from apps.catalog.models import Brand, Category, Product
from apps.coupons.models import Coupon
from apps.orders.models import Order, ShippingMethod

User = get_user_model()


class StorefrontSmokeTests(TestCase):
    """Pages must render for a brand new visitor."""

    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Essentials")
        cls.brand = Brand.objects.create(name="Aurora")
        cls.product = Product.objects.create(
            name="Aurora Hoodie",
            sku="HOOD-001",
            category=cls.category,
            brand=cls.brand,
            price=Decimal("40.00"),
            stock_quantity=10,
            is_featured=True,
        )
        ShippingMethod.objects.create(
            name="Standard shipping",
            code="standard",
            cost=Decimal("5.00"),
            free_over=Decimal("75.00"),
            estimated_days="3-5 days",
        )

    def test_homepage_renders(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aurora Hoodie")

    def test_shop_list_and_filters(self):
        response = self.client.get(reverse("catalog:shop"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aurora Hoodie")

        response = self.client.get(reverse("catalog:shop"), {"q": "hoodie"})
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("catalog:category", args=[self.category.slug]))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("catalog:brand", args=[self.brand.slug]))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("catalog:brands"))
        self.assertEqual(response.status_code, 200)

        response = self.client.get(reverse("catalog:search"), {"q": "aurora"})
        self.assertEqual(response.status_code, 200)

    def test_product_detail_renders(self):
        response = self.client.get(reverse("catalog:detail", args=[self.product.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.product.name)

    def test_unknown_page_uses_404_template(self):
        response = self.client.get("/definitely/not/a/page/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page not found", status_code=404)

    def test_shop_toolbar_categories_endpoint(self):
        response = self.client.get(reverse("catalog:suggest"), {"q": "aur"})
        self.assertEqual(response.status_code, 200)

    def test_header_subnavigation_renders(self):
        """Desktop sub-nav holds Home/Shop/Categories/Deals/Brands and is
        hidden on mobile where the offcanvas carries the same links."""
        response = self.client.get(reverse("core:home"))
        html = response.content.decode()

        # Second header tier exists and is desktop-only.
        self.assertContains(response, 'class="au-subnav d-none d-lg-block"')
        self.assertEqual(html.count("au-subnav-link"), 5)

        # All five destinations are present.
        self.assertContains(response, reverse("core:home"))
        self.assertContains(response, reverse("catalog:shop"))
        self.assertContains(response, reverse("catalog:brands"))
        self.assertIn('href="#"', html)  # Categories dropdown trigger

        # Offcanvas gained the previously-missing Categories + Deals entries.
        self.assertContains(response, 'id="mobileNavCategories"')
        self.assertContains(response, reverse("catalog:shop") + "?sort=discount")

    def test_header_subnavigation_active_states(self):
        """The Deals tab highlights on the discounted shop view."""
        response = self.client.get(reverse("catalog:shop"), {"sort": "discount"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'au-subnav-link active" href="{}?sort=discount"'.format(
                reverse("catalog:shop")
            ),
        )


class AccountSmokeTests(TestCase):
    def test_register_login_dashboard(self):
        response = self.client.post(reverse("accounts:register"), {
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
            "phone": "+1 (555) 000-0000",
            "password1": "S3cure-passw0rd!",
            "password2": "S3cure-passw0rd!",
            "accept_terms": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

        # Auto-logged-in: dashboard renders and verification/welcome mail sent.
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jane")
        self.assertEqual(len(mail.outbox), 2)

        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {
            "username": "jane@example.com",
            "password": "S3cure-passw0rd!",
            "remember": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_login_required_pages_redirect(self):
        for name in ("accounts:dashboard", "accounts:profile", "orders:list"):
            response = self.client.get(reverse(name))
            self.assertIn(response.status_code, (302, 403), name)
            if response.status_code == 302:
                self.assertIn("/accounts/login/", response.url)

    def test_password_reset_sends_email(self):
        User.objects.create_user(
            username="resetme", email="resetme@example.com",
            password="whatever123",
        )
        response = self.client.post(reverse("accounts:password_reset"), {
            "email": "resetme@example.com",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset", mail.outbox[0].subject.lower())

    def test_profile_and_addresses(self):
        user = User.objects.create_user(
            username="profile", email="profile@example.com",
            password="whatever123", first_name="Pat",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse("accounts:address_create"), {
            "address_type": "shipping",
            "full_name": "Pat Doe",
            "phone": "+1 (555) 111-2222",
            "address_line1": "10 Main St",
            "city": "Springfield",
            "state": "IL",
            "postal_code": "62704",
            "country": "United States",
            "is_default": "on",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(user.addresses.count(), 1)

        response = self.client.get(reverse("accounts:addresses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "10 Main St")


class CartAndCheckoutSmokeTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Gear")
        self.product = Product.objects.create(
            name="Trail Backpack",
            sku="BAG-001",
            category=self.category,
            price=Decimal("40.00"),
            stock_quantity=10,
        )
        ShippingMethod.objects.create(
            name="Standard shipping",
            code="standard",
            cost=Decimal("5.00"),
            free_over=Decimal("75.00"),
        )
        self.coupon = Coupon.objects.create(
            code="SAVE10",
            type=Coupon.Type.PERCENTAGE,
            value=Decimal("10"),
            is_active=True,
        )

    def _add_to_cart(self, quantity=3):
        return self.client.post(reverse("cart:add"), {
            "product": self.product.pk,
            "quantity": quantity,
        })

    def test_guest_cart_coupon_and_totals(self):
        from apps.cart.services import cart_totals

        self._add_to_cart(quantity=3)

        # Items + subtotal come from the header drawer fragment.
        response = self.client.get(reverse("cart:mini"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trail Backpack")
        self.assertContains(response, "$120.00")

        # Apply the coupon; discount is recomputed server-side.
        response = self.client.post("/cart/coupon/apply/", {"coupon_code": "SAVE10"})
        self.assertEqual(response.status_code, 302)

        cart = Cart.objects.get()
        self.assertEqual(cart.coupon_code, "SAVE10")
        totals = cart_totals(cart)
        self.assertEqual(totals["discount"], Decimal("12.00"))
        self.assertEqual(totals["discounted_subtotal"], Decimal("108.00"))

        # The drawer fragment shows the applied coupon and its discount.
        response = self.client.get(reverse("cart:mini"))
        self.assertContains(response, "SAVE10")
        self.assertContains(response, "$12.00")

        # Quantity update
        item = cart.items.first()
        self.client.post(reverse("cart:update"), {
            "item_id": item.pk, "quantity": 2,
        })
        self.assertEqual(cart.items.first().quantity, 2)

    def test_authenticated_checkout_creates_order_and_clears_stock(self):
        user = User.objects.create_user(
            username="buyer", email="buyer@example.com",
            password="whatever123", first_name="Bud",
        )
        self.client.force_login(user)
        self._add_to_cart(quantity=3)
        applied = self.client.post("/cart/coupon/apply/", {"coupon_code": "SAVE10"})
        self.assertEqual(applied.status_code, 302)

        response = self.client.get(reverse("checkout:start"))
        self.assertEqual(response.status_code, 200)

        quote = self.client.get(reverse("checkout:start"), {
            "quote": "1", "method": "standard",
        })
        self.assertEqual(quote.status_code, 200)
        self.assertEqual(quote.json()["shipping"], "$0.00")

        response = self.client.post(reverse("checkout:place"), {
            "email": user.email,
            "full_name": "Bud Buyer",
            "phone": "+1 (555) 333-4444",
            "address_line1": "99 Market St",
            "city": "Portland",
            "state": "OR",
            "postal_code": "97201",
            "country": "United States",
            "same_as_shipping": "on",
            "shipping_method": "standard",
            "payment_method": "cod",
            "notes": "Leave at the door",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith("/orders/"))

        order = Order.objects.get()
        self.assertEqual(order.status, Order.Status.PENDING)
        self.assertEqual(order.subtotal, Decimal("120.00"))
        self.assertEqual(order.discount, Decimal("12.00"))
        self.assertEqual(order.total, Decimal("108.00"))
        self.assertEqual(order.payment_method, "cod")
        self.assertEqual(order.user, user)

        # Cart cleared, stock decremented, confirmation email sent.
        from apps.cart.models import CartItem

        self.assertEqual(CartItem.objects.count(), 0)
        self.assertEqual(
            Product.objects.get(pk=self.product.pk).stock_quantity, 7
        )
        self.assertEqual(len(mail.outbox), 1)

        # Authenticated user can view the order page.
        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trail Backpack")

    def test_authenticated_checkout_and_order_pages(self):
        user = User.objects.create_user(
            username="buyer", email="buyer@example.com",
            password="whatever123", first_name="Bud",
        )
        self.client.force_login(user)
        self._add_to_cart(quantity=3)

        response = self.client.post(reverse("checkout:place"), {
            "email": user.email,
            "full_name": "Bud Buyer",
            "phone": "+1 (555) 555-5555",
            "address_line1": "1 Checkout Ave",
            "city": "Austin",
            "state": "TX",
            "postal_code": "78701",
            "country": "United States",
            "same_as_shipping": "on",
            "shipping_method": "standard",
            "payment_method": "cod",
        })
        self.assertEqual(response.status_code, 302)
        order_url = response.url

        response = self.client.get(order_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trail Backpack")

        response = self.client.get(reverse("orders:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, Order.objects.get().order_number)

        # Invoice endpoint streams a PDF.
        order_number = Order.objects.get().order_number
        response = self.client.get(reverse("orders:invoice", args=[order_number]))
        self.assertEqual(response.status_code, 200)

        # Customer notification + admin notification were created.
        response = self.client.get(reverse("notifications:list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "placed")

        # Cancel: stock must come back.
        response = self.client.post(
            reverse("orders:cancel", args=[order_number]),
            {"reason": "changed my mind"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            Product.objects.get(pk=self.product.pk).stock_quantity, 10
        )
        self.assertEqual(
            Order.objects.get().status, Order.Status.CANCELLED
        )
