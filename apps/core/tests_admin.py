"""Django admin smoke: the superuser admin index lists the key models."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class DjangoAdminIndexTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="root", email="root@example.com", password="s3cret-pass"
        )

    def test_admin_index_lists_core_models(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        for app in ("Products, categories", "Orders, checkout",
                    "Discount coupons", "Payment gateway",
                    "Product reviews", "notifications"):
            self.assertContains(response, app)
        for model in ("Product", "Order", "Coupon", "Payment", "Review",
                      "Notification"):
            self.assertContains(response, model)

    def test_admin_branding(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertContains(response, "Aurora Store Administration")
        self.assertContains(response, "Store management")
