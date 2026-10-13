"""Dark-mode theming: pre-paint script, toggle button, assets."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class ThemeRenderingTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("core:home"))
        self.html = self.response.content.decode()

    def test_prepaint_theme_script_present(self):
        # Sets data-theme + data-bs-theme before first paint (no flash).
        self.assertIn('localStorage.getItem("au-theme")', self.html)
        self.assertIn('prefers-color-scheme: dark', self.html)
        self.assertIn("data-bs-theme", self.html)

    def test_theme_color_meta_present(self):
        self.assertIn('name="theme-color"', self.html)

    def test_dark_css_and_theme_js_loaded_versioned(self):
        self.assertIn("css/dark.css?v=", self.html)
        self.assertIn("js/theme.js?v=", self.html)
        # dark.css must come after main.css so its overrides win.
        self.assertLess(
            self.html.index("css/main.css"), self.html.index("css/dark.css")
        )

    def test_toggle_button_rendered(self):
        self.assertIn("data-theme-toggle", self.html)
        self.assertIn("data-theme-icon", self.html)
        self.assertIn("data-to-dark=", self.html)
        self.assertIn("data-to-light=", self.html)
        self.assertIn("Switch to dark mode", self.html)
        self.assertIn("Switch to light mode", self.html)


class ManagementThemeTests(TestCase):
    """The staff portal (templates/management/base.html) honours the same theme."""

    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            username="terra", email="terra@example.com",
            password="s3cret-pass", role=User.Role.STAFF,
            is_staff=True, is_superuser=True,
        )

    def setUp(self):
        self.client.force_login(self.staff)
        self.html = self.client.get(reverse("dashboard:home")).content.decode()

    def test_prepaint_theme_script_present(self):
        self.assertIn('localStorage.getItem("au-theme")', self.html)
        self.assertIn("data-bs-theme", self.html)

    def test_dark_css_loaded_after_management_css(self):
        self.assertIn("css/dark.css?v=", self.html)
        self.assertLess(
            self.html.index("css/management.css"), self.html.index("css/dark.css")
        )

    def test_theme_js_loaded(self):
        self.assertIn("js/theme.js?v=", self.html)

    def test_toggle_button_rendered(self):
        self.assertIn("data-theme-toggle", self.html)
        self.assertIn("data-theme-icon", self.html)
        self.assertIn("Switch to dark mode", self.html)
        self.assertIn("Switch to light mode", self.html)
