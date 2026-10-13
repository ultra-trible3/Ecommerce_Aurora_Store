"""Role-based access: each staff group sees only its own portal sections."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


def make_staff(username, group_name):
    user = User.objects.create_user(
        username=username, email=f"{username}@example.com",
        password="s3cret-pass", role=User.Role.STAFF, is_staff=True,
    )
    group = Group.objects.get(name=group_name)
    user.groups.add(group)
    return user


class RolePermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.inventory = make_staff("ingrid", "Inventory Manager")
        cls.support = make_staff("sam", "Support Agent")
        cls.content = make_staff("clara", "Content Manager")
        cls.orders = make_staff("omar", "Order Manager")

    def _status(self, user, name, args=None):
        self.client.force_login(user)
        response = self.client.get(reverse(name, args=args or []))
        self.client.logout()
        return response.status_code

    def test_inventory_manager_access(self):
        self.assertEqual(self._status(self.inventory, "dashboard:home"), 200)
        self.assertEqual(self._status(self.inventory, "dashboard:inventory"), 200)
        self.assertEqual(self._status(self.inventory, "dashboard:products"), 200)
        self.assertEqual(self._status(self.inventory, "dashboard:coupons"), 403)
        self.assertEqual(self._status(self.inventory, "dashboard:settings"), 403)
        self.assertEqual(self._status(self.inventory, "dashboard:customers"), 403)

    def test_support_agent_access(self):
        self.assertEqual(self._status(self.support, "dashboard:orders"), 200)
        self.assertEqual(self._status(self.support, "dashboard:reviews"), 200)
        self.assertEqual(self._status(self.support, "dashboard:notifications"), 200)
        self.assertEqual(self._status(self.support, "dashboard:products"), 403)
        self.assertEqual(self._status(self.support, "dashboard:inventory"), 403)
        self.assertEqual(self._status(self.support, "dashboard:coupons"), 403)

    def test_content_manager_access(self):
        self.assertEqual(self._status(self.content, "dashboard:products"), 200)
        self.assertEqual(self._status(self.content, "dashboard:reviews"), 200)
        self.assertEqual(self._status(self.content, "dashboard:subscribers"), 200)
        self.assertEqual(self._status(self.content, "dashboard:orders"), 403)
        self.assertEqual(self._status(self.content, "dashboard:inventory"), 403)

    def test_order_manager_access(self):
        self.assertEqual(self._status(self.orders, "dashboard:orders"), 200)
        self.assertEqual(self._status(self.orders, "dashboard:coupons"), 200)
        self.assertEqual(self._status(self.orders, "dashboard:products"), 403)
        self.assertEqual(self._status(self.orders, "dashboard:settings"), 403)

    def test_sidebar_hides_unallowed_sections(self):
        self.client.force_login(self.support)
        response = self.client.get(reverse("dashboard:home"))
        body = response.content.decode()
        self.assertIn(f'href="{reverse("dashboard:orders")}"', body)
        self.assertNotIn(f'href="{reverse("dashboard:products")}"', body)
        self.assertNotIn(f'href="{reverse("dashboard:settings")}"', body)
        self.assertNotIn(f'href="{reverse("dashboard:inventory")}"', body)

    def test_admin_group_holds_every_permission(self):
        admin_group = Group.objects.get(name="Admin")
        self.assertGreater(admin_group.permissions.count(), 100)
