"""Tests for the homepage Deals & Promotions mosaic."""
from decimal import Decimal

from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from apps.catalog.deals import DEALS
from apps.catalog.models import Category, Product


class DealsMosaicTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Essentials")
        cls.product = Product.objects.create(
            name="Trail Backpack",
            sku="BAG-001",
            category=cls.category,
            price=Decimal("49.00"),
            stock_quantity=5,
        )

    def test_home_renders_deals_section(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deals &amp; Promotions")
        for deal in DEALS:
            self.assertContains(response, str(deal["eyebrow"]))
            self.assertContains(response, str(deal["title"]))
            self.assertContains(response, deal["badge"])
            self.assertContains(response, str(deal["cta"]))

    def test_every_tile_renders_in_the_mosaic(self):
        response = self.client.get(reverse("core:home"))
        html = response.content.decode()
        self.assertEqual(html.count('class="au-deal tone-'), len(DEALS))
        for deal in DEALS:
            self.assertIn(f"is-{deal['size']}", html)

    def test_tiles_link_to_real_shop_filters(self):
        shop = reverse("catalog:shop")
        response = self.client.get(reverse("core:home"))
        html = response.content.decode()
        for deal in DEALS:
            expected = f"{shop}?{deal['query']}" if deal["query"] else shop
            self.assertIn(f'href="{expected}"', html)

    def test_no_broken_image_paths(self):
        """Tiles ship without images, so no <img> artwork is emitted."""
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "au-deal-media")

    def test_deals_section_precedes_recently_viewed(self):
        session = self.client.session
        session["recently_viewed"] = [self.product.slug]
        session.save()

        response = self.client.get(reverse("core:home"))
        html = response.content.decode()
        self.assertIn("au-deals-section", html)
        self.assertIn("Recently viewed", html)
        self.assertLess(
            html.index("au-deals-section"), html.index("Recently viewed")
        )

    def test_component_renders_with_a_custom_list(self):
        html = render_to_string(
            "includes/deals_mosaic.html", {"home_deals": [DEALS[0]]}
        )
        self.assertIn("au-deals", html)
        self.assertIn("is-hero", html)
        self.assertEqual(html.count('class="au-deal tone-'), 1)

    def test_component_renders_nothing_without_deals(self):
        html = render_to_string("includes/deals_mosaic.html", {"home_deals": []})
        self.assertNotIn("au-deals", html)

    def test_mosaic_is_responsive_in_css(self):
        from django.contrib.staticfiles import finders

        path = finders.find("css/main.css")
        with open(path, encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn(".au-deals", css)
        # Desktop 4 columns, tablet 2, mobile single column (no overflow).
        self.assertIn("grid-template-columns: repeat(4, minmax(0, 1fr))", css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", css)
        self.assertIn("grid-template-columns: 1fr", css)
        self.assertIn("prefers-reduced-motion: reduce", css)
