"""Regression tests for the security fixes in TEST-AUDIT.md (C1, H1)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class VerifyEmailTokenTests(TestCase):
    """C1 — an empty/short-circuit verification token must never authenticate."""

    def test_blank_token_is_rejected_and_does_not_authenticate(self):
        # Two users: one already verified (token None), one never verified.
        User.objects.create_user(
            username="first", email="first@example.com", password="p-assw0rd!"
        )
        pending = User.objects.create_user(
            username="pending", email="pending@example.com", password="p-assw0rd!"
        )
        self.assertIsNone(pending.verification_token)

        response = self.client.get(reverse("accounts:verify_email") + "?token=")

        self.assertRedirects(response, reverse("accounts:login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)
        pending.refresh_from_db()
        self.assertFalse(pending.email_verified)

    def test_missing_token_is_rejected(self):
        response = self.client.get(reverse("accounts:verify_email"))
        self.assertRedirects(response, reverse("accounts:login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_blank_token_does_not_log_in_as_a_real_token_holder(self):
        user = User.objects.create_user(
            username="real", email="real@example.com", password="p-assw0rd!"
        )
        user.generate_verification_token()
        user.save(update_fields=["verification_token"])

        response = self.client.get(reverse("accounts:verify_email") + "?token=")
        self.assertRedirects(response, reverse("accounts:login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_valid_token_verifies_and_clears_the_token(self):
        user = User.objects.create_user(
            username="verify", email="verify@example.com", password="p-assw0rd!"
        )
        token = user.generate_verification_token()
        user.save(update_fields=["verification_token"])

        response = self.client.get(
            reverse("accounts:verify_email") + f"?token={token}"
        )
        self.assertEqual(response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.email_verified)
        self.assertIsNone(user.verification_token)

    def test_cleared_token_cannot_be_replayed(self):
        user = User.objects.create_user(
            username="replay", email="replay@example.com", password="p-assw0rd!"
        )
        token = user.generate_verification_token()
        user.save(update_fields=["verification_token"])
        self.client.get(reverse("accounts:verify_email") + f"?token={token}")
        self.client.logout()

        # Re-using the same token after it was consumed must fail.
        response = self.client.get(reverse("accounts:verify_email") + f"?token={token}")
        self.assertRedirects(response, reverse("accounts:login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


class SafeNextRedirectTests(TestCase):
    """H1 — ``?next=`` must only ever point at the current host."""

    def _register_payload(self, email="new@example.com"):
        return {
            "first_name": "New",
            "last_name": "User",
            "email": email,
            "phone": "",
            "password1": "sup3r-secret-pass",
            "password2": "sup3r-secret-pass",
            "accept_terms": "on",
        }

    def test_register_ignores_external_next(self):
        url = reverse("accounts:register") + "?next=https://evil.example.com/phish"
        response = self.client.post(url, self._register_payload(), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_register_ignores_protocol_relative_next(self):
        url = reverse("accounts:register") + "?next=//evil.example.com"
        response = self.client.post(url, self._register_payload("other@example.com"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_register_allows_same_host_next(self):
        url = reverse("accounts:register") + "?next=/cart/"
        response = self.client.post(url, self._register_payload("cart@example.com"), follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/cart/")

    def test_login_ignores_protocol_relative_next(self):
        User.objects.create_user(
            username="login", email="login@example.com", password="sup3r-secret-pass"
        )
        url = reverse("accounts:login") + "?next=//evil.example.com"
        response = self.client.post(
            url, {"username": "login@example.com", "password": "sup3r-secret-pass"},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_login_ignores_absolute_external_next(self):
        User.objects.create_user(
            username="login2", email="login2@example.com", password="sup3r-secret-pass"
        )
        url = reverse("accounts:login") + "?next=https://evil.example.com"
        response = self.client.post(
            url, {"username": "login2@example.com", "password": "sup3r-secret-pass"},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_login_allows_same_host_next(self):
        User.objects.create_user(
            username="login3", email="login3@example.com", password="sup3r-secret-pass"
        )
        url = reverse("accounts:login") + "?next=/accounts/"
        response = self.client.post(
            url, {"username": "login3@example.com", "password": "sup3r-secret-pass"},
            follow=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/")
