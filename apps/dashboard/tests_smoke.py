"""Smoke tests: every management portal page must render for staff."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Brand, Category, Product
from apps.coupons.models import Coupon
from apps.notifications.models import NewsletterSubscriber, Notification
from apps.orders.models import Order
from apps.reviews.models import Review

User = get_user_model()


class ManagementPortalSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            username="boss", email="boss@example.com", password="s3cret-pass"
        )
        cls.customer = User.objects.create_user(
            username="shopper", email="shopper@example.com",
            password="s3cret-pass", role=User.Role.CUSTOMER,
        )

        cls.category = Category.objects.create(name="Gear")
        cls.brand = Brand.objects.create(name="Aurora")
        cls.product = Product.objects.create(
            name="Trail Backpack", sku="BAG-001",
            category=cls.category, brand=cls.brand,
            price=Decimal("49.00"), stock_quantity=3,
        )
        cls.coupon = Coupon.objects.create(
            code="WELCOME5", type=Coupon.Type.FIXED,
            value=Decimal("5"), is_active=True,
        )
        cls.order = Order.objects.create(
            order_number="ORD-20260101-0001",
            user=cls.customer,
            email=cls.customer.email,
            shipping_full_name="Shopper One",
            shipping_address_line1="10 Main St",
            shipping_city="Springfield",
            shipping_postal_code="62704",
            subtotal=Decimal("49.00"),
            total=Decimal("49.00"),
        )
        cls.review = Review.objects.create(
            product=cls.product, user=cls.customer,
            rating=5, body="Great bag, highly recommended.",
        )
        NewsletterSubscriber.objects.create(email="news@example.com")
        Notification.objects.create(
            user=cls.staff, type=Notification.Type.SYSTEM,
            title="New order", body="Something happened",
        )

    def _pages(self):
        return [
            ("dashboard:home", []),
            ("dashboard:products", []),
            ("dashboard:product_create", []),
            ("dashboard:product_edit", [self.product.pk]),
            ("dashboard:product_detail", [self.product.pk]),
            ("dashboard:categories", []),
            ("dashboard:category_create", []),
            ("dashboard:category_edit", [self.category.pk]),
            ("dashboard:brands", []),
            ("dashboard:brand_create", []),
            ("dashboard:brand_edit", [self.brand.pk]),
            ("dashboard:orders", []),
            ("dashboard:order_detail", [self.order.order_number]),
            ("dashboard:order_edit", [self.order.order_number]),
            ("dashboard:order_invoice", [self.order.order_number]),
            ("dashboard:customers", []),
            ("dashboard:customer_detail", [self.customer.pk]),
            ("dashboard:customer_edit", [self.customer.pk]),
            ("dashboard:subscribers", []),
            ("dashboard:notifications", []),
            ("dashboard:coupons", []),
            ("dashboard:coupon_create", []),
            ("dashboard:coupon_edit", [self.coupon.pk]),
            ("dashboard:reviews", []),
            ("dashboard:inventory", []),
            ("dashboard:settings", []),
        ]

    def test_every_page_renders_for_superuser(self):
        self.client.force_login(self.staff)
        for name, args in self._pages():
            with self.subTest(page=name):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 200, name)

    def test_portal_blocks_customers(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 403)

    def test_portal_redirects_anonymous(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_report_pages_render_with_section_tabs(self):
        """Each report page renders and marks its own tab active."""
        self.client.force_login(self.staff)
        pages = {
            "dashboard:reports": "Overview",
            "dashboard:reports_sales": "Sales Details",
            "dashboard:reports_categories": "By Category",
            "dashboard:reports_customers": "Customers",
            "dashboard:reports_products": "Products",
        }
        for name, label in pages.items():
            with self.subTest(route=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200, name)
                html = response.content.decode()
                self.assertIn("mg-tabs", html)
                self.assertIn('role="tab"', html)
                # Exactly one tab carries the active state and points at this page.
                self.assertEqual(html.count("mg-tab active"), 1, name)
                self.assertIn(label, html)
                self.assertEqual(html.count('aria-current="page"'), 1, name)

    def test_report_pdfs_download(self):
        """Every report page offers a branded, downloadable PDF."""
        self.client.force_login(self.staff)
        routes = (
            "dashboard:reports_pdf",
            "dashboard:reports_sales_pdf",
            "dashboard:reports_categories_pdf",
            "dashboard:reports_customers_pdf",
            "dashboard:reports_products_pdf",
        )
        for name in routes:
            with self.subTest(route=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200, name)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertIn("attachment", response["Content-Disposition"])
                content = b"".join(response.streaming_content)
                self.assertTrue(content.startswith(b"%PDF"))

    def test_report_pdf_renders_in_arabic(self):
        """Arabic reports use the bundled RTL font and shaped text."""
        from apps.core import pdf_theme

        script = "\u0627\u0644\u0625\u064a\u0631\u0627\u062f\u0627\u062a"  # الإيرادات
        shaped = pdf_theme._shape_arabic(script)
        self.assertNotEqual(shaped, script)
        self.assertTrue(
            any("\ufe70" <= ch <= "\ufeff" for ch in shaped),
            "Arabic text should be reshaped into presentation forms",
        )

        self.client.force_login(self.staff)
        # LocaleMiddleware activates the language from Accept-Language, the
        # same mechanism the language switcher relies on.
        response = self.client.get(
            reverse("dashboard:reports_pdf"), HTTP_ACCEPT_LANGUAGE="ar"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        content = b"".join(response.streaming_content)
        self.assertTrue(content.startswith(b"%PDF"))
        # The embedded, subset Arabic font is the bundled Amiri family.
        self.assertIn(b"Amiri", content)

    def test_home_renders_charts_and_json_encoded_series(self):
        """Chart series travel in json_script blocks: the language swap must
        recognise them as data (type="application/json") and never rewrite
        them, or JSON.parse breaks and the charts go blank."""
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'js/i18n.js')
        for canvas in ("revenueChart", "statusChart", "monthChart"):
            self.assertContains(response, f'id="{canvas}"')
        for payload in ("revenue-data", "month-data", "status-data"):
            self.assertContains(
                response, f'<script id="{payload}" type="application/json">'
            )

    def test_order_status_transition(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("dashboard:order_status", args=[self.order.order_number]),
            {"status": "confirmed", "note": "paid at counter"},
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CONFIRMED)
        self.assertEqual(self.order.status_history.count(), 1)

    def test_order_edit_saves_details(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("dashboard:order_edit", args=[self.order.order_number]),
            {
                "email": "new.address@example.com",
                "guest_name": "",
                "guest_phone": "+1 555 0100",
                "shipping_full_name": "Shopper One",
                "shipping_phone": "+1 555 0100",
                "shipping_address_line1": "20 Oak Ave",
                "shipping_address_line2": "",
                "shipping_city": "Shelbyville",
                "shipping_state": "IL",
                "shipping_country": "United States",
                "shipping_postal_code": "62704",
                "notes": "Customer asked for gift wrap",
                "internal_notes": "Verified address by phone",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.email, "new.address@example.com")
        self.assertEqual(self.order.shipping_city, "Shelbyville")
        self.assertEqual(self.order.internal_notes, "Verified address by phone")
        # The edit is audited in the activity log (internal-only entry).
        self.assertEqual(self.order.status_history.count(), 1)
        entry = self.order.status_history.get()
        self.assertFalse(entry.is_customer_visible)
        self.assertEqual(entry.actor, self.staff)

    def test_order_delete_removes_unpaid_order(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("dashboard:order_delete", args=[self.order.order_number])
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard:orders"))
        self.assertFalse(Order.objects.filter(pk=self.order.pk).exists())

    def test_order_delete_blocked_for_paid_orders(self):
        self.order.payment_status = "paid"
        self.order.save(update_fields=["payment_status"])
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("dashboard:order_delete", args=[self.order.order_number])
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse("dashboard:order_detail", args=[self.order.order_number]),
        )
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())

    def test_product_create(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("dashboard:product_create"), {
            "name_en": "Camp Lantern", "name_ar": "فانوس المخيم",
            "slug": "camp-lantern", "sku": "LTN-001",
            "category": self.category.pk, "brand": self.brand.pk,
            "price": "29.99", "sale_price": "", "cost_price": "",
            "stock_quantity": "12", "min_stock_level": "5",
            "weight": "", "dimensions": "",
            "short_description_en": "Bright and light.",
            "short_description_ar": "مضيء وخفيف.",
            "full_description_en": "A very bright lantern.",
            "full_description_ar": "فانوس ساطع جداً.",
            "status": "active",
        })
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(sku="LTN-001")
        self.assertEqual(product.name_en, "Camp Lantern")
        self.assertEqual(product.name_ar, "فانوس المخيم")
        # The legacy base column mirrors the English copy (raw SQL/exports).
        self.assertEqual(product.__dict__["name"], "Camp Lantern")
        self.assertEqual(product.slug, "camp-lantern")

    def test_product_create_without_slug_generates_english_slug(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("dashboard:product_create"), {
            "name_en": "Solar Charger", "name_ar": "شاحن شمسي",
            "slug": "", "sku": "SOL-001",
            "category": self.category.pk, "brand": "",
            "price": "19.99", "sale_price": "", "cost_price": "",
            "stock_quantity": "4", "min_stock_level": "5",
            "weight": "", "dimensions": "",
            "status": "active",
        })
        self.assertEqual(response.status_code, 302)
        product = Product.objects.get(sku="SOL-001")
        self.assertEqual(product.slug, "solar-charger")

    def test_product_form_shows_english_and_arabic_inputs(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("dashboard:product_edit", args=[self.product.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "js/i18n.js")
        self.assertContains(response, 'name="name_en"')
        self.assertContains(response, 'name="name_ar"')
        self.assertContains(response, 'name="short_description_en"')
        self.assertContains(response, 'name="short_description_ar"')
        self.assertContains(response, 'name="full_description_en"')
        self.assertContains(response, 'name="full_description_ar"')

        form = response.context["form"]
        self.assertTrue(form.fields["name_en"].required)
        self.assertFalse(form.fields["name_ar"].required)
        self.assertEqual(
            form.fields["name_ar"].widget.attrs.get("dir"), "rtl"
        )

    def test_category_and_brand_forms_show_both_languages(self):
        self.client.force_login(self.staff)
        pages = (
            (reverse("dashboard:category_edit", args=[self.category.pk]), "category"),
            (reverse("dashboard:brand_edit", args=[self.brand.pk]), "brand"),
        )
        for url, kind in pages:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            for field in (
                "name_en", "name_ar", "description_en", "description_ar",
            ):
                self.assertContains(
                    response, f'name="{field}"',
                    msg_prefix=f"{kind} form is missing {field}",
                )
            self.assertTrue(response.context["form"].fields["name_en"].required)

    def test_brand_create_twice_keeps_unique_english_name(self):
        """The base ``name`` column is UNIQUE: it must never stay empty."""
        self.client.force_login(self.staff)
        url = reverse("dashboard:brand_create")
        for english, arabic in (("Northwind", "رياح الشمال"), ("Kestrel", "صقر")):
            response = self.client.post(url, {
                "name_en": english, "name_ar": arabic, "slug": "",
                "description_en": "", "description_ar": "",
            })
            self.assertEqual(response.status_code, 302)

        brand = Brand.objects.get(name_en="Kestrel")
        self.assertEqual(brand.__dict__["name"], "Kestrel")
        self.assertEqual(brand.slug, "kestrel")

    def test_stock_adjustment(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("dashboard:inventory_adjust"), {
            "product": self.product.pk,
            "quantity": "7",
            "transaction_type": "purchase",
            "note": "Supplier delivery",
        })
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 10)

    def test_review_approve_updates_rating(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("dashboard:review_moderate", args=[self.review.pk]),
            {"action": "approve", "next_status": "pending"},
        )
        self.assertEqual(response.status_code, 302)
        self.review.refresh_from_db()
        self.assertEqual(self.review.status, Review.Status.APPROVED)
        self.product.refresh_from_db()
        self.assertEqual(float(self.product.rating_average), 5.0)

    def test_settings_save(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("dashboard:settings"), {
            "store_name": "Nomad Supply",
            "store_email": "hi@nomad.test",
            "store_phone": "+1 (555) 100-2000",
            "currency_symbol": "$",
            "low_stock_threshold": "4",
            "orders_from_email": "orders@nomad.test",
        })
        self.assertEqual(response.status_code, 302)
        from apps.notifications.models import Setting

        self.assertEqual(Setting.get("store_name"), "Nomad Supply")

    def test_customer_edit_saves_profile(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("dashboard:customer_edit", args=[self.customer.pk]),
            {
                "first_name": "Shop",
                "last_name": "Per",
                "email": "shopper@example.com",
                "username": "shopper",
                "phone": "+1 555 0134",
                "email_verified": "on",
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.first_name, "Shop")
        self.assertEqual(self.customer.phone, "+1 555 0134")
        self.assertTrue(self.customer.email_verified)

    def test_customer_edit_rejects_duplicate_email(self):
        User.objects.create_user(
            username="other", email="taken@example.com",
            password="s3cret-pass", role=User.Role.CUSTOMER,
        )
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("dashboard:customer_edit", args=[self.customer.pk]),
            {
                "first_name": "Shopper", "last_name": "One",
                "email": "taken@example.com", "username": "shopper",
                "phone": "", "email_verified": "", "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_customer_delete_removes_user_but_keeps_orders(self):
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("dashboard:customer_delete", args=[self.customer.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.customer.pk).exists())
        # Financial history survives: orders are unlinked, not deleted.
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())
        self.order.refresh_from_db()
        self.assertIsNone(self.order.user)

    def test_customer_delete_refuses_staff_accounts(self):
        """Staff/superuser accounts are never deletable through the portal."""
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("dashboard:customer_delete", args=[self.staff.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.staff.pk).exists())
