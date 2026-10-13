"""Tests for the "frequently bought together" recommendation service."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product
from apps.catalog.services import frequently_bought_together
from apps.orders.models import Order, OrderItem


class FrequentlyBoughtTogetherTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Gear")
        cls.a = Product.objects.create(
            name="Product A", sku="FBT-A", category=cls.category,
            price=Decimal("10.00"), stock_quantity=5,
        )
        cls.b = Product.objects.create(
            name="Product B", sku="FBT-B", category=cls.category,
            price=Decimal("10.00"), stock_quantity=5, sold_count=10,
        )
        cls.c = Product.objects.create(
            name="Product C", sku="FBT-C", category=cls.category,
            price=Decimal("10.00"), stock_quantity=5,
        )
        cls.other = Product.objects.create(
            name="Product Z", sku="FBT-Z", category=cls.category,
            price=Decimal("10.00"), stock_quantity=5,
        )

    def _order(self, number, products):
        order = Order.objects.create(
            order_number=number,
            email="buyer@example.com",
            shipping_full_name="Buyer",
            shipping_address_line1="1 Test St",
            shipping_city="Testville",
            shipping_postal_code="00000",
        )
        for product in products:
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                product_sku=product.sku,
                unit_price=product.price,
                quantity=1,
            )
        return order

    def test_co_purchased_products_are_ranked_by_frequency(self):
        # A is bought with B twice and C once.
        self._order("O-1", [self.a, self.b])
        self._order("O-2", [self.a, self.b])
        self._order("O-3", [self.a, self.c])

        result = list(frequently_bought_together(self.a))

        self.assertEqual(result[0], self.b)
        self.assertIn(self.c, result)
        self.assertNotIn(self.a, result)      # never recommends itself
        self.assertNotIn(self.other, result)  # never co-purchased

    def test_empty_when_product_has_no_orders(self):
        self.assertEqual(list(frequently_bought_together(self.other)), [])

    def test_inactive_products_are_excluded(self):
        self._order("O-4", [self.a, self.other])
        self.other.status = Product.Status.ARCHIVED
        self.other.save(update_fields=["status"])

        self.assertNotIn(self.other, list(frequently_bought_together(self.a)))

    def test_detail_page_renders_recommendation_section(self):
        self._order("O-5", [self.a, self.b])
        response = self.client.get(reverse("catalog:detail", args=[self.a.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Frequently bought together")
        self.assertContains(response, self.b.name)
