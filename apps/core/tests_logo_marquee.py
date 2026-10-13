"""Tests for the reusable LogoMarquee component (home page integration)."""
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse

from apps.catalog.brand_logos import (
    BRAND_LOGOS,
    MARQUEE_SETTING_KEY,
    get_brand_logos,
    parse_brand_logos,
    serialize_brand_logos,
)
from apps.notifications.models import Setting

User = get_user_model()


class LogoMarqueeTests(TestCase):
    def test_home_renders_logo_marquee(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Trusted by leading brands")
        self.assertContains(response, "au-marquee")
        for logo in BRAND_LOGOS:
            self.assertContains(response, 'alt="%s"' % logo["name"])

    def test_track_is_duplicated_for_seamless_loop(self):
        """Four identical copies => the shift loops with no gap on any screen."""
        response = self.client.get(reverse("core:home"))
        html = response.content.decode()
        self.assertEqual(
            html.count('class="au-marquee-logo"'), 4 * len(BRAND_LOGOS)
        )

    def test_reduced_motion_is_respected_in_css(self):
        from django.contrib.staticfiles import finders

        path = finders.find("css/main.css")
        with open(path, encoding="utf-8") as fh:
            css = fh.read()
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn("@keyframes au-marquee-scroll", css)
        # The loop must be a linear, infinite, seamless one-copy translate.
        self.assertIn("translateX(calc(-100% / var(--au-marquee-copies)))", css)
        self.assertIn("--au-marquee-copies: 4", css)

    def test_component_accepts_a_custom_list(self):
        html = render_to_string(
            "includes/logo_marquee.html",
            {"marquee_logos": [{"name": "Solo", "image": "images/brands/acme.svg"}]},
        )
        self.assertIn('alt="Solo"', html)
        self.assertEqual(html.count('class="au-marquee-logo"'), 4)
        self.assertNotIn('alt="Nimbus"', html)

    def test_component_renders_nothing_without_logos(self):
        html = render_to_string("includes/logo_marquee.html", {"marquee_logos": []})
        self.assertNotIn("au-marquee", html)

    def test_arabic_translation(self):
        response = self.client.get(reverse("core:home"), HTTP_ACCEPT_LANGUAGE="ar")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "موثوق به من قِبل أبرز العلامات التجارية")


class BrandLogosHelpersTests(TestCase):
    def test_parse_and_serialize_round_trip(self):
        text = serialize_brand_logos(BRAND_LOGOS)
        self.assertEqual(parse_brand_logos(text), BRAND_LOGOS)

    def test_parse_accepts_pipe_comma_and_bare_paths(self):
        logos = parse_brand_logos(
            "Acme | images/brands/acme.svg\n"
            "Nimbus, images/brands/nimbus.svg\n"
            "images/brands/solo.svg\n"
            "\n"
        )
        self.assertEqual(
            logos,
            [
                {"name": "Acme", "image": "images/brands/acme.svg"},
                {"name": "Nimbus", "image": "images/brands/nimbus.svg"},
                {"name": "solo.svg", "image": "images/brands/solo.svg"},
            ],
        )

    def test_get_brand_logos_falls_back_when_unset(self):
        self.assertEqual(get_brand_logos(), list(BRAND_LOGOS))

    def test_get_brand_logos_uses_setting_and_ignores_blank(self):
        Setting.set(MARQUEE_SETTING_KEY, "Solo | images/brands/acme.svg")
        self.assertEqual(
            get_brand_logos(),
            [{"name": "Solo", "image": "images/brands/acme.svg"}],
        )
        Setting.set(MARQUEE_SETTING_KEY, "   ")
        self.assertEqual(get_brand_logos(), list(BRAND_LOGOS))


class LogoMarqueeDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_superuser(
            username="boss", email="boss@example.com", password="s3cret-pass"
        )

    def setUp(self):
        self.client.force_login(self.staff)

    def test_settings_page_prefills_current_logos(self):
        response = self.client.get(reverse("dashboard:settings"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acme | images/brands/acme.svg")

    def test_saving_settings_updates_storefront_marquee(self):
        response = self.client.post(
            reverse("dashboard:settings"),
            {MARQUEE_SETTING_KEY: "Solo | images/brands/acme.svg"},
        )
        self.assertRedirects(response, reverse("dashboard:settings"))
        self.assertEqual(Setting.get(MARQUEE_SETTING_KEY), "Solo | images/brands/acme.svg")

        home = self.client.get(reverse("core:home"))
        self.assertContains(home, 'alt="Solo"')
        self.assertNotContains(home, 'alt="Nimbus"')

    def test_saving_blank_restores_builtin_logos(self):
        Setting.set(MARQUEE_SETTING_KEY, "Solo | images/brands/acme.svg")
        self.client.post(reverse("dashboard:settings"), {MARQUEE_SETTING_KEY: ""})
        home = self.client.get(reverse("core:home"))
        self.assertContains(home, 'alt="Acme"')
        self.assertNotContains(home, 'alt="Solo"')
