"""English <-> Arabic language switching: cookie, rendering and search."""
from decimal import Decimal

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext, ngettext

from apps.catalog.models import Category, Product
from apps.core import i18n_catalog


def _contains_arabic(value):
    return any("\u0600" <= ch <= "\u06ff" for ch in value)


class LanguageToggleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Gear", name_ar="معدات")
        cls.product = Product.objects.create(
            name="Trail Backpack",
            name_ar="حقيبة الظهر",
            sku="BAG-LANG-1",
            category=cls.category,
            price=Decimal("49.00"),
            stock_quantity=3,
        )

    def _toggle(self, code, next_url="/"):
        return self.client.post(
            reverse("set_language"), {"language": code, "next": next_url}
        )

    def test_switcher_and_script_are_rendered(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, 'id="au-lang-form"')
        self.assertContains(response, "js/i18n.js")
        self.assertContains(response, 'name="language" value="en"')
        self.assertContains(response, 'name="language" value="ar"')

    def test_toggle_sets_language_cookie_and_rtl_document(self):
        response = self._toggle("ar")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies["django_language"].value, "ar")

        response = self.client.get(reverse("core:home"))
        self.assertContains(response, '<html lang="ar"')
        self.assertContains(response, 'dir="rtl"')

    def test_language_choice_persists_across_requests(self):
        self._toggle("ar")
        response = self.client.get(reverse("catalog:shop"))
        self.assertContains(response, '<html lang="ar"')

    def test_toggle_back_to_english(self):
        self._toggle("ar")
        self._toggle("en")
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, '<html lang="en"')

    def test_product_detail_renders_in_arabic(self):
        """URLs have no language prefix, so the slug lookup must not change."""
        self._toggle("ar")
        url = reverse("catalog:detail", args=[self.product.slug])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "حقيبة الظهر")

    def test_product_name_follows_the_active_language(self):
        url = reverse("catalog:detail", args=[self.product.slug])
        response = self.client.get(url)
        self.assertContains(response, "Trail Backpack")

        self._toggle("ar")
        response = self.client.get(url)
        self.assertContains(response, "حقيبة الظهر")

    def test_arabic_falls_back_to_the_english_name(self):
        product = Product.objects.create(
            name="English Only",
            sku="BAG-LANG-2",
            category=self.category,
            price=Decimal("10.00"),
            stock_quantity=1,
        )
        self._toggle("ar")
        response = self.client.get(
            reverse("catalog:detail", args=[product.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "English Only")

    def test_search_matches_names_in_both_languages(self):
        with translation.override("en"):
            self.assertIn(self.product, Product.objects.search("backpack"))
            self.assertIn(self.product, Product.objects.search("حقيبة"))

        with translation.override("ar"):
            self.assertIn(self.product, Product.objects.search("backpack"))
            self.assertIn(self.product, Product.objects.search("حقيبة"))

    def test_slug_is_identical_in_both_languages(self):
        with translation.override("en"):
            english_url = self.product.get_absolute_url()
        with translation.override("ar"):
            arabic_url = self.product.get_absolute_url()
        self.assertEqual(english_url, arabic_url)

    def test_price_keeps_dollar_in_arabic(self):
        """Currency symbol and Western digits stay unchanged in Arabic."""
        self._toggle("ar")
        response = self.client.get(
            reverse("catalog:detail", args=[self.product.slug])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "حقيبة الظهر")
        self.assertContains(response, "49.00")
        self.assertContains(response, "$")

    def test_shop_page_renders_in_both_languages(self):
        """Regression: `trans ... as` on a child's top level never ran, so the
        meta_description block referenced an undefined variable."""
        for code in ("en", "ar"):
            self._toggle(code)
            response = self.client.get(reverse("catalog:shop"))
            self.assertEqual(response.status_code, 200)


class LanguageSwapScriptTests(SimpleTestCase):
    """The instant toggle re-parses the page in the *same* JS realm.

    Re-running an inline script that declares a top-level ``const`` throws a
    SyntaxError and drops the whole block -- that is what used to blank the
    dashboard charts after switching to Arabic.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js = (settings.BASE_DIR / "static" / "js" / "i18n.js").read_text(
            encoding="utf-8"
        )

    def test_swap_rewraps_inline_scripts_before_document_write(self):
        self.assertIn("function wrapInlineScripts(html)", self.js)
        self.assertIn("document.write(wrapInlineScripts(html))", self.js)
        self.assertIn("(function(){", self.js)

    def test_swap_keeps_json_payloads_and_external_scripts_intact(self):
        # json_script output is read back with JSON.parse(), so the wrapper
        # must never touch it; <script src> tags must keep their src.
        self.assertIn("application", self.js)
        self.assertIn("json", self.js)
        self.assertIn(r"/\bsrc\s*=/i", self.js)

    def test_swap_recovers_with_a_real_reload_when_a_script_throws(self):
        self.assertIn("reload()", self.js)


class ArabicMessageTests(SimpleTestCase):
    """Core labels resolve to Arabic under the ar locale."""

    def test_core_labels_render_in_arabic(self):
        with translation.override("ar"):
            self.assertEqual(gettext("Add to cart"), "أضف للسلة")
            self.assertEqual(gettext("Shopping cart"), "سلة التسوق")
            self.assertEqual(gettext("Store profile"), "ملف المتجر")
            self.assertEqual(gettext("Your cart is empty."), "سلة التسوق فارغة.")
            self.assertEqual(gettext("Stock"), "المخزون")

    def test_literal_percent_is_preserved_in_translation(self):
        with translation.override("ar"):
            self.assertEqual(gettext("Up to 60% off"), "خصم يصل إلى 60%")
            self.assertEqual(gettext("{}% off"), "خصم {}%")

    def test_placeholder_sets_survive_translation(self):
        """%(name)s / %(count)s tokens used by views must not be lost."""
        with translation.override("ar"):
            self.assertEqual(
                gettext("Welcome back, %(name)s!"), "مرحبًا بعودتك، %(name)s!"
            )
            self.assertEqual(
                gettext("Only %(count)s in stock."), "%(count)s فقط في المخزون."
            )
            self.assertEqual(
                gettext("Low stock: %(name)s"), "مخزون منخفض: %(name)s"
            )

    def test_arabic_ngettext_plural_forms(self):
        with translation.override("ar"):
            one = ngettext("%(count)s item", "%(count)s items", 1) % {"count": 1}
            three = ngettext("%(count)s item", "%(count)s items", 3) % {"count": 3}
            dual = ngettext("%(count)s item", "%(count)s items", 2) % {"count": 2}
            many = ngettext("%(count)s item", "%(count)s items", 11) % {"count": 11}
        self.assertEqual(one, "1 عنصر")
        self.assertEqual(dual, "عنصران")
        self.assertEqual(three, "3 عناصر")
        self.assertEqual(many, "11 عنصرًا")

    def test_english_is_never_leaked_by_the_catalog(self):
        """The en catalog must be an identity map, not stale content."""
        with translation.override("en"):
            self.assertEqual(gettext("Store profile"), "Store profile")
            self.assertEqual(gettext("Repeat password"), "Repeat password")
            self.assertEqual(gettext("Email address"), "Email address")
            self.assertEqual(gettext("Added to cart"), "Added to cart")


class JsCatalogTests(SimpleTestCase):
    """Client-side messages (apps/core/i18n_catalog.py) resolve in Arabic."""

    def test_every_js_message_has_an_arabic_translation(self):
        # Resolve the msgids under the English locale so the lookup really
        # goes through the catalog (str() on a lazy proxy would otherwise
        # already return the Arabic form under the ar locale).
        with translation.override("en"):
            sources = [str(msg) for msg in i18n_catalog.JS_MESSAGES]
        with translation.override("ar"):
            for source in sources:
                translated = gettext(source)
                self.assertTrue(
                    _contains_arabic(translated),
                    "JS message not translated into Arabic: %r" % source,
                )

    def test_positional_placeholders_survive_js_translation(self):
        with translation.override("en"):
            sources = [str(msg) for msg in i18n_catalog.JS_MESSAGES]
        with translation.override("ar"):
            for source in sources:
                translated = gettext(source)
                self.assertEqual(
                    source.count("%s"),
                    translated.count("%s"),
                    f"JS message lost/reordered %s placeholders: {source!r}",
                )

    def test_js_catalog_context_processor_localizes(self):
        from django.test import RequestFactory

        from apps.core.context_processors import js_catalog

        factory = RequestFactory()
        with translation.override("ar"):
            catalog = js_catalog(factory.get("/"))["JS_CATALOG"]
        # Keys stay English (what JS passes to window.t); values are Arabic.
        self.assertIn("Shopping cart", catalog)
        self.assertEqual(catalog["Shopping cart"], "سلة التسوق")
        self.assertTrue(_contains_arabic(catalog["Shopping cart"]))


class CompiledCatalogTests(SimpleTestCase):
    """The compiled Arabic catalog carries no empty translations."""

    def test_arabic_catalog_has_no_empty_msgstr(self):
        ar = translation.trans_real.translation("ar")
        catalog = ar._catalog
        empty = [
            key
            for key in catalog.keys()
            if catalog[key] in (b"", "") and key not in (b"", "")
        ]
        self.assertEqual(empty, [])

    def test_ar_po_catalog_file_is_fully_translated(self):
        from django.conf import settings

        po_path = settings.BASE_DIR / "locale" / "ar" / "LC_MESSAGES" / "django.po"
        text = po_path.read_text(encoding="utf-8")
        # A quick structural sanity check on top of the compiled catalog test:
        # the file must not contain fuzzy markers or obsolete entries.
        self.assertNotIn("#, fuzzy", text)
        self.assertNotIn("#| msgid", text)
