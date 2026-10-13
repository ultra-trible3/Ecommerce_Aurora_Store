"""Management portal: adding colour options (variants) to a product."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Attribute, AttributeValue, Category, Product

User = get_user_model()


class ProductColorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            username="boss", email="boss@example.com", password="s3cret-pass"
        )
        cls.category = Category.objects.create(name="Gear")

    def setUp(self):
        self.client.force_login(self.staff)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _payload(self, rows, initial_forms=0, **overrides):
        data = {
            "name_en": "Aurora Tee",
            "name_ar": "تيشيرت أورورا",
            "slug": "",
            "sku": "TEE-100",
            "category": self.category.pk,
            "brand": "",
            "price": "20.00",
            "sale_price": "",
            "cost_price": "",
            "stock_quantity": "0",
            "min_stock_level": "5",
            "weight": "",
            "dimensions": "",
            "status": "active",
            "short_description_en": "",
            "short_description_ar": "",
            "full_description_en": "",
            "full_description_ar": "",
            "colors-TOTAL_FORMS": str(len(rows)),
            "colors-INITIAL_FORMS": str(initial_forms),
            "colors-MIN_NUM_FORMS": "0",
            "colors-MAX_NUM_FORMS": "1000",
        }
        for index, row in enumerate(rows):
            for key, value in row.items():
                data[f"colors-{index}-{key}"] = value
        data.update(overrides)
        return data

    def _create_with_colors(self):
        return self.client.post(
            reverse("dashboard:product_create"),
            self._payload([
                {"name": "Red", "color_hex": "#ff0000",
                 "stock_quantity": "3", "price": "", "sku": ""},
                {"name": "Blue", "color_hex": "#0000ff",
                 "stock_quantity": "5", "price": "", "sku": ""},
            ]),
        )

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------
    def test_create_product_with_colors_creates_variants(self):
        response = self._create_with_colors()
        self.assertEqual(response.status_code, 302)

        product = Product.objects.get(sku="TEE-100")
        self.assertEqual(product.variants.count(), 2)
        # Variant stock drives the product's available quantity.
        self.assertEqual(product.available_quantity, 8)

        red = product.variants.get(name_en="Red")
        self.assertEqual(red.stock_quantity, 3)
        self.assertEqual(red.attributes.get().color_hex, "#ff0000")
        self.assertTrue(red.is_active)

        # Both variants get a unique, product-derived SKU.
        skus = set(product.variants.values_list("sku", flat=True))
        self.assertEqual(len(skus), 2)
        self.assertTrue(all(s.startswith("TEE-100") for s in skus))

    def test_color_attribute_and_values_are_created(self):
        self._create_with_colors()
        attribute = Attribute.objects.get(name_en="Color")
        self.assertEqual(attribute.name, "Color")  # legacy base column
        self.assertTrue(
            AttributeValue.objects.filter(
                attribute=attribute, value_en="Red", color_hex="#ff0000"
            ).exists()
        )

    def test_color_values_are_filterable_on_the_shop(self):
        self._create_with_colors()
        # ``shop_context`` powers the storefront colour facet.
        self.assertTrue(
            AttributeValue.objects.filter(
                attribute__name_en__iexact="color",
                variants__is_active=True,
                color_hex="#ff0000",
            ).exists()
        )

    def test_storefront_renders_the_color_swatch(self):
        self._create_with_colors()
        product = Product.objects.get(sku="TEE-100")
        response = self.client.get(product.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "#ff0000")
        self.assertContains(response, "Red")

    def test_create_without_color_section_still_works(self):
        """Legacy/API posts without the colour formset must keep working."""
        response = self.client.post(
            reverse("dashboard:product_create"),
            {
                "name_en": "Plain Mug",
                "name_ar": "كوب",
                "slug": "",
                "sku": "MUG-1",
                "category": self.category.pk,
                "brand": "",
                "price": "9.00",
                "sale_price": "",
                "cost_price": "",
                "stock_quantity": "7",
                "min_stock_level": "5",
                "weight": "",
                "dimensions": "",
                "status": "active",
            },
        )
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(sku="MUG-1")
        self.assertEqual(product.variants.count(), 0)

    def test_blank_color_rows_are_ignored(self):
        response = self.client.post(
            reverse("dashboard:product_create"),
            self._payload([
                {"name": "Red", "color_hex": "#ff0000",
                 "stock_quantity": "2", "price": "", "sku": ""},
                {"name": "", "color_hex": "#000000",
                 "stock_quantity": "0", "price": "", "sku": ""},
            ]),
        )
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(sku="TEE-100")
        self.assertEqual(product.variants.count(), 1)

    def test_invalid_hex_is_rejected(self):
        response = self.client.post(
            reverse("dashboard:product_create"),
            self._payload([
                {"name": "Weird", "color_hex": "#zzzzzz",
                 "stock_quantity": "1", "price": "", "sku": ""},
            ]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Product.objects.filter(sku="TEE-100").exists())

    # ------------------------------------------------------------------
    # edit
    # ------------------------------------------------------------------
    def test_edit_updates_adds_and_deletes_colors(self):
        self._create_with_colors()
        product = Product.objects.get(sku="TEE-100")
        red = product.variants.get(name_en="Red")
        blue = product.variants.get(name_en="Blue")

        response = self.client.post(
            reverse("dashboard:product_edit", args=[product.pk]),
            self._payload(
                [
                    {"variant_id": red.pk, "name": "Red", "color_hex": "#ff0000",
                     "stock_quantity": "9", "price": "22.00", "sku": red.sku},
                    {"variant_id": blue.pk, "name": "Blue", "color_hex": "#0000ff",
                     "stock_quantity": "5", "price": "", "sku": blue.sku,
                     "DELETE": "on"},
                    {"variant_id": "", "name": "Green", "color_hex": "#00ff00",
                     "stock_quantity": "2", "price": "", "sku": ""},
                ],
                initial_forms=2,
            ),
        )
        self.assertEqual(response.status_code, 302)

        product.refresh_from_db()
        self.assertEqual(product.variants.count(), 2)
        red.refresh_from_db()
        self.assertEqual(red.stock_quantity, 9)
        self.assertEqual(red.price, Decimal("22.00"))
        self.assertFalse(product.variants.filter(pk=blue.pk).exists())
        green = product.variants.get(name_en="Green")
        self.assertEqual(green.attributes.get().color_hex, "#00ff00")

    def test_edit_page_prefills_existing_colors(self):
        self._create_with_colors()
        product = Product.objects.get(sku="TEE-100")
        response = self.client.get(
            reverse("dashboard:product_edit", args=[product.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="Red"')
        self.assertContains(response, 'value="#ff0000"')

    def test_customer_cannot_post_colors(self):
        customer = User.objects.create_user(
            username="shopper", email="shopper@example.com",
            password="s3cret-pass", role=User.Role.CUSTOMER,
        )
        self.client.force_login(customer)
        response = self.client.post(
            reverse("dashboard:product_create"),
            self._payload([
                {"name": "Red", "color_hex": "#ff0000",
                 "stock_quantity": "1", "price": "", "sku": ""},
            ]),
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Product.objects.filter(sku="TEE-100").exists())
