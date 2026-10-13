"""Header notification dropdown: mark-as-read, poll endpoint, mini fragment."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.notifications.models import Notification

User = get_user_model()

XHR = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class NotificationPollTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="notifuser",
            email="notif@example.com",
            password="whatever123",
        )

    def test_poll_requires_login(self):
        response = self.client.get(reverse("notifications:poll"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["authenticated"])

    def test_poll_returns_baseline_without_since(self):
        n = Notification.objects.create(
            user=self.user, type="order", title="Order shipped"
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("notifications:poll"))
        data = response.json()
        self.assertTrue(data["authenticated"])
        self.assertEqual(data["unread"], 1)
        self.assertEqual(data["latest_id"], n.pk)
        self.assertEqual(data["new"], [])

    def test_poll_reports_new_items_since(self):
        old = Notification.objects.create(user=self.user, title="Old one")
        self.client.force_login(self.user)
        # baseline
        self.client.get(reverse("notifications:poll"))
        fresh = Notification.objects.create(user=self.user, title="Fresh one")

        response = self.client.get(reverse("notifications:poll"), {"since": old.pk})
        data = response.json()
        self.assertEqual(data["unread"], 2)
        self.assertEqual(data["latest_id"], fresh.pk)
        self.assertEqual([n["id"] for n in data["new"]], [fresh.pk])
        self.assertEqual(data["new"][0]["title"], "Fresh one")

    def test_poll_is_never_cached(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("notifications:poll"))
        self.assertIn("no-store", response["Cache-Control"])


class MarkReadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="markme",
            email="markme@example.com",
            password="whatever123",
        )
        self.n1 = Notification.objects.create(user=self.user, title="First")
        self.n2 = Notification.objects.create(user=self.user, title="Second")

    def test_mark_read_xhr_returns_unread_count(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notifications:mark_read", args=[self.n1.pk]), {}, **XHR
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["unread"], 1)
        self.n1.refresh_from_db()
        self.assertTrue(self.n1.is_read)

    def test_mark_read_xhr_requires_login(self):
        response = self.client.post(
            reverse("notifications:mark_read", args=[self.n1.pk]), {}, **XHR
        )
        self.assertEqual(response.status_code, 401)

    def test_mark_all_read_xhr(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("notifications:mark_all_read"), {}, **XHR
        )
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["unread"], 0)
        self.assertFalse(Notification.objects.filter(is_read=False).exists())


class DropdownMarkupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dropuser",
            email="drop@example.com",
            password="whatever123",
        )

    def test_header_renders_notification_wiring(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "data-notif-poll")
        self.assertContains(response, reverse("notifications:poll"))
        self.assertContains(response, "data-notif-list")
        self.assertContains(response, reverse("notifications:mini"))
        self.assertContains(response, "data-notif-read-all")

    def test_unread_item_has_read_button_and_url(self):
        n = Notification.objects.create(user=self.user, title="Needs reading")
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "data-notif-read-btn")
        self.assertContains(response, "data-notif-item")
        self.assertContains(response, reverse("notifications:mark_read", args=[n.pk]))

    def test_read_item_has_no_button(self):
        n = Notification.objects.create(user=self.user, title="Already read")
        n.is_read = True
        n.save(update_fields=["is_read"])
        self.client.force_login(self.user)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "data-notif-item")
        self.assertNotContains(response, "data-notif-read-btn")

    def test_mini_fragment(self):
        Notification.objects.create(user=self.user, title="Mini item")
        self.client.force_login(self.user)
        response = self.client.get(reverse("notifications:mini"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mini item")
        self.assertContains(response, "data-notif-read-btn")
        self.assertIn("no-store", response["Cache-Control"])
