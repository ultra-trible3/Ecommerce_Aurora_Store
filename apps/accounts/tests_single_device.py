"""Single-device login: a new login signs out the previous device.

See ``apps.accounts.signals`` (binding) and
``apps.core.middleware.SingleDeviceSessionMiddleware`` (enforcement).
"""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()

PASSWORD = "device-pass-123!"


class SingleDeviceLoginTests(TestCase):
    """A user may only stay signed in on one device at a time."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="deviceuser",
            email="device@example.com",
            password=PASSWORD,
        )

    def _login(self, client, email="device@example.com"):
        return client.post(
            reverse("accounts:login"),
            {"username": email, "password": PASSWORD},
        )

    # -- binding ----------------------------------------------------------

    def test_login_records_the_active_session_key(self):
        client = Client()
        response = self._login(client)

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.active_session_key)
        self.assertEqual(self.user.active_session_key, client.session.session_key)

    def test_force_login_also_binds_the_session(self):
        """The ``user_logged_in`` signal covers every login path."""
        client = Client()
        client.force_login(self.user)

        self.user.refresh_from_db()
        self.assertEqual(self.user.active_session_key, client.session.session_key)

    def test_device_id_cookie_is_issued_once_and_kept(self):
        client = Client()
        first = client.get("/")
        self.assertIn("device_id", first.cookies)
        device_id = first.cookies["device_id"].value
        self.assertTrue(device_id)

        # The same browser keeps the same id on later requests.
        second = client.get("/")
        self.assertNotIn("device_id", second.cookies)

        client.post(
            reverse("accounts:login"),
            {"username": self.user.email, "password": PASSWORD},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.active_device_id, device_id)

    # -- enforcement ------------------------------------------------------

    def test_second_login_signs_out_the_first_device(self):
        first, second = Client(), Client()

        self._login(first)
        self.assertEqual(first.get(reverse("accounts:dashboard")).status_code, 200)

        # A second device logs in with the same account.
        self._login(second)

        # The first device is now rejected and sent to the login page.
        response = first.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
        self.assertIn("kicked=1", response.url)

        # The new device is unaffected.
        self.assertEqual(second.get(reverse("accounts:dashboard")).status_code, 200)

    def test_same_device_stays_signed_in_across_requests(self):
        client = Client()
        self._login(client)

        for _ in range(3):
            self.assertEqual(
                client.get(reverse("accounts:dashboard")).status_code, 200
            )

    def test_unbound_session_is_not_enforced(self):
        """Sessions that predate the feature (no bound key) are left alone."""
        client = Client()
        client.force_login(self.user)
        User.objects.filter(pk=self.user.pk).update(active_session_key="")

        self.assertEqual(
            client.get(reverse("accounts:dashboard")).status_code, 200
        )

    def test_kicked_ajax_request_returns_json_flag(self):
        first, second = Client(), Client()
        self._login(first)
        self._login(second)

        response = first.get(
            reverse("notifications:poll"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["authenticated"])
        self.assertTrue(data["session_kicked"])

    def test_kicked_ajax_request_reports_authenticated_false(self):
        """The existing fragments key off ``authenticated: false``."""
        first = Client()
        self._login(first)
        User.objects.filter(pk=self.user.pk).update(active_session_key="rotated")

        response = first.get(
            reverse("notifications:poll"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertFalse(response.json()["authenticated"])

    def test_management_portal_is_enforced_too(self):
        staff = User.objects.create_user(
            username="boss",
            email="boss@example.com",
            password=PASSWORD,
            role=User.Role.STAFF,
            is_staff=True,
        )
        first, second = Client(), Client()

        self._login(first, email=staff.email)
        self.assertEqual(first.get(reverse("dashboard:home")).status_code, 200)

        self._login(second, email=staff.email)

        response = first.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("kicked=1", response.url)
        self.assertEqual(second.get(reverse("dashboard:home")).status_code, 200)

    def test_login_page_shows_kicked_notice(self):
        response = self.client.get(reverse("accounts:login") + "?kicked=1")
        self.assertContains(response, "signed in on another device")

    def test_kicked_marker_cookie_renders_and_clears_notice(self):
        self.client.cookies["au_kicked"] = "1"
        response = self.client.get(reverse("accounts:login"))

        self.assertContains(response, "signed in on another device")
        # Consumed once: the marker is expired on the way out.
        self.assertIn("au_kicked", response.cookies)
        self.assertEqual(response.cookies["au_kicked"].value, "")

    def test_kicked_poll_response_sets_marker_cookie(self):
        first, second = Client(), Client()
        self._login(first)
        self._login(second)

        response = first.get(
            reverse("notifications:poll"),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertTrue(response.json()["session_kicked"])
        self.assertIn("au_kicked", response.cookies)
        self.assertEqual(response.cookies["au_kicked"].value, "1")
