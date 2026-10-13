"""Tests for the session-based product compare feature."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product


class CompareTests(TestCase):
    """Compare list lives in the session — guests can use it too."""

    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Gear")
        cls.p1 = Product.objects.create(
            name="Tent", sku="CMP-1", category=category,
            price=Decimal("100.00"), stock_quantity=5,
        )
        cls.p2 = Product.objects.create(
            name="Backpack", sku="CMP-2", category=category,
            price=Decimal("50.00"), stock_quantity=3,
        )
        cls.p3 = Product.objects.create(
            name="Headlamp", sku="CMP-3", category=category,
            price=Decimal("30.00"), stock_quantity=0,
        )
        cls.p4 = Product.objects.create(
            name="Stove", sku="CMP-4", category=category,
            price=Decimal("70.00"), stock_quantity=2,
        )
        cls.p5 = Product.objects.create(
            name="Map", sku="CMP-5", category=category,
            price=Decimal("10.00"), stock_quantity=1,
        )

    def _toggle(self, slug):
        return self.client.post(reverse("compare:toggle"), {"slug": slug})

    def _set_session(self, slugs):
        session = self.client.session
        session["compare"] = slugs
        session.save()

    # -- toggle -----------------------------------------------------------
    def test_toggle_adds_and_removes(self):
        response = self._toggle(self.p1.slug)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["added"])
        self.assertEqual(data["count"], 1)
        self.assertEqual(self.client.session["compare"], [self.p1.slug])

        data = self._toggle(self.p1.slug).json()
        self.assertFalse(data["added"])
        self.assertEqual(data["count"], 0)
        self.assertEqual(self.client.session["compare"], [])

    def test_toggle_accepts_product_pk(self):
        data = self._toggle(str(self.p1.pk)).json()
        self.assertTrue(data["added"])
        self.assertEqual(self.client.session["compare"], [self.p1.slug])

    def test_toggle_unknown_product_is_bad_request(self):
        response = self._toggle("does-not-exist")
        self.assertEqual(response.status_code, 400)

    def test_compare_is_limited_to_four(self):
        for product in (self.p1, self.p2, self.p3, self.p4):
            self.assertTrue(self._toggle(product.slug).json()["added"])

        response = self._toggle(self.p5.slug)
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["ok"])
        self.assertIn("up to 4", data["message"])
        self.assertEqual(data["count"], 4)
        self.assertEqual(len(self.client.session["compare"]), 4)

    # -- page ---------------------------------------------------------------
    def test_page_renders_products_in_session_order(self):
        self._set_session([self.p2.slug, self.p1.slug])
        response = self.client.get(reverse("compare:list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["products"]), [self.p2, self.p1]
        )
        self.assertContains(response, self.p1.name)
        self.assertContains(response, self.p2.name)

    def test_page_shows_empty_state(self):
        response = self.client.get(reverse("compare:list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["products"]), [])
        self.assertContains(response, "Nothing to compare yet")
        self.assertContains(
            response,
            "Tap the compare icon on any product to line them up side by side.",
        )
        # The shared empty-state include must render *only* the compare copy,
        # not the other empty states it used to bundle (regression).
        for other in (
            "Your cart is empty",
            "No orders yet",
            "No results found",
            "No products match your filters",
            "Your wishlist is empty",
            "No notifications",
        ):
            self.assertNotContains(response, other)

    def test_archived_products_are_dropped_and_session_cleaned(self):
        self.p2.status = Product.Status.ARCHIVED
        self.p2.save(update_fields=["status"])
        self._set_session([self.p1.slug, self.p2.slug])

        response = self.client.get(reverse("compare:list"))
        self.assertEqual(
            list(response.context["products"]), [self.p1]
        )
        self.assertEqual(self.client.session["compare"], [self.p1.slug])

    def test_best_price_and_rating_highlights(self):
        self.p2.rating_average = Decimal("4.80")
        self.p2.rating_count = 12
        self.p2.save(update_fields=["rating_average", "rating_count"])
        self._set_session([self.p1.slug, self.p2.slug])

        response = self.client.get(reverse("compare:list"))
        self.assertEqual(response.context["best_price_pk"], self.p2.pk)
        self.assertEqual(response.context["best_rating_pk"], self.p2.pk)

    # -- remove / clear -----------------------------------------------------
    def test_remove_product(self):
        self._set_session([self.p1.slug, self.p2.slug])
        response = self.client.post(
            reverse("compare:remove", args=[self.p1.slug])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["compare"], [self.p2.slug])

    def test_remove_product_ajax_returns_json(self):
        self._set_session([self.p1.slug])
        response = self.client.post(
            reverse("compare:remove", args=[self.p1.slug]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "count": 0})

    def test_clear_all(self):
        self._set_session([self.p1.slug, self.p2.slug])
        response = self.client.post(reverse("compare:clear"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["compare"], [])

    # -- header badge -------------------------------------------------------
    def test_header_context_exposes_count_and_slugs(self):
        self._set_session([self.p1.slug])
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.context["compare_count"], 1)
        self.assertEqual(response.context["compare_slugs"], [self.p1.slug])

        # Product cards can render the active state.
        response = self.client.get(reverse("catalog:shop"))
        self.assertEqual(response.context["compare_count"], 1)
