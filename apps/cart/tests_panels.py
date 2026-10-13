"""Header side-drawer endpoints and markup (cart / wishlist drawer)."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cart.models import Cart, WishlistItem
from apps.catalog.models import Category, Product, ProductVariant

User = get_user_model()

XHR = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class MiniCartPanelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Gear")
        self.product = Product.objects.create(
            name="Trail Backpack",
            sku="BAG-MINI",
            category=self.category,
            price=Decimal("40.00"),
            stock_quantity=10,
        )

    def test_empty_cart_panel(self):
        response = self.client.get(reverse("cart:mini"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your cart is empty")
        self.assertContains(response, reverse("catalog:shop"))

    def test_cart_panel_lists_items_with_actions(self):
        self.client.post(reverse("cart:add"), {
            "product": self.product.pk, "quantity": 2,
        })
        response = self.client.get(reverse("cart:mini"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trail Backpack")
        self.assertContains(response, "$80.00")
        self.assertContains(response, reverse("cart:update"))
        self.assertContains(response, reverse("cart:remove"))
        self.assertContains(response, reverse("checkout:start"))

    def test_cart_panel_with_variant_uses_product_weight(self):
        """A variant in the cart must not crash the drawer (regression)."""
        self.product.weight = Decimal("1.50")
        self.product.save(update_fields=["weight"])
        variant = ProductVariant.objects.create(
            product=self.product, name="Large", sku="BAG-MINI-L",
            stock_quantity=4,
        )
        self.client.post(reverse("cart:add"), {
            "product": self.product.pk, "variant": variant.pk, "quantity": 2,
        })

        response = self.client.get(reverse("cart:mini"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Large")

        cart = Cart.objects.get()
        item = cart.items.get()
        # Variants inherit the product's weight.
        self.assertEqual(float(item.weight), 3.0)
        self.assertEqual(float(cart.total_weight), 3.0)

    def test_cart_panel_with_variant_and_no_product_weight(self):
        variant = ProductVariant.objects.create(
            product=self.product, name="Small", sku="BAG-MINI-S",
            stock_quantity=3,
        )
        self.client.post(reverse("cart:add"), {
            "product": self.product.pk, "variant": variant.pk, "quantity": 1,
        })
        response = self.client.get(reverse("cart:mini"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(float(Cart.objects.get().total_weight), 0.0)

    def test_header_renders_drawer_triggers(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-drawer-open")
        self.assertContains(response, 'data-drawer-key="cart"')
        self.assertContains(response, 'data-drawer-key="wishlist"')
        self.assertContains(response, reverse("cart:mini"))
        self.assertContains(response, reverse("wishlist:mini"))
        self.assertContains(response, "data-drawer-url")
        self.assertContains(response, 'id="au-drawer"')

    def test_removed_pages_redirect_home(self):
        for url in ("/cart/", "/wishlist/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, url)
            self.assertEqual(response["Location"], "/", url)

    def test_mini_fragments_are_never_cached(self):
        for name in ("cart:mini", "wishlist:mini"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response["Cache-Control"], name)

    def test_coupon_apply_xhr_returns_json(self):
        from apps.coupons.models import Coupon

        Coupon.objects.create(
            code="SAVE10",
            type="fixed",
            value=Decimal("10.00"),
            is_active=True,
        )
        self.client.post(reverse("cart:add"), {
            "product": self.product.pk, "quantity": 2,
        })
        response = self.client.post(
            reverse("cart:apply_coupon"), {"coupon_code": "SAVE10"}, **XHR
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertIn("SAVE10", data["message"])
        cart = Cart.objects.get()
        self.assertEqual(cart.coupon_code, "SAVE10")


class MiniWishlistPanelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Gear")
        self.product = Product.objects.create(
            name="Rain Poncho",
            sku="PON-MINI",
            category=self.category,
            price=Decimal("25.00"),
            stock_quantity=5,
        )
        self.user = User.objects.create_user(
            username="paneluser",
            email="panel@example.com",
            password="whatever123",
        )

    def test_anonymous_panel_shows_sign_in(self):
        response = self.client.get(reverse("wishlist:mini"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in")
        self.assertNotContains(response, "Rain Poncho")

    def test_wishlist_panel_lists_items(self):
        item = WishlistItem.objects.create(user=self.user, product=self.product)
        self.client.force_login(self.user)
        response = self.client.get(reverse("wishlist:mini"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rain Poncho")
        self.assertContains(response, reverse("wishlist:move", args=[item.pk]))
        self.assertContains(response, reverse("wishlist:remove", args=[item.pk]))

    def test_header_wishlist_badge(self):
        WishlistItem.objects.create(user=self.user, product=self.product)
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'data-wishlist-count')
        self.assertContains(response, ">1</span>")

    def test_remove_xhr_returns_json(self):
        item = WishlistItem.objects.create(user=self.user, product=self.product)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("wishlist:remove", args=[item.pk]), {}, **XHR
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 0)
        self.assertFalse(WishlistItem.objects.filter(pk=item.pk).exists())

    def test_remove_plain_post_redirects(self):
        item = WishlistItem.objects.create(user=self.user, product=self.product)
        self.client.force_login(self.user)
        response = self.client.post(reverse("wishlist:remove", args=[item.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(WishlistItem.objects.filter(pk=item.pk).exists())

    def test_move_to_cart_xhr(self):
        item = WishlistItem.objects.create(user=self.user, product=self.product)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("wishlist:move", args=[item.pk]), {}, **XHR
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["cart_count"], 1)
        self.assertFalse(WishlistItem.objects.filter(pk=item.pk).exists())
        cart = Cart.objects.get(user=self.user)
        self.assertTrue(cart.items.filter(product=self.product).exists())

    def test_remove_xhr_requires_login(self):
        item = WishlistItem.objects.create(user=self.user, product=self.product)
        response = self.client.post(
            reverse("wishlist:remove", args=[item.pk]), {}, **XHR
        )
        self.assertEqual(response.status_code, 401)
        self.assertTrue(WishlistItem.objects.filter(pk=item.pk).exists())
