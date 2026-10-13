"""Notifications, newsletter subscribers and store settings."""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _


class AbandonedCart(models.Model):
    """Track carts that haven't converted to orders for recovery emails."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="abandoned_carts",
    )
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    email = models.EmailField()
    cart_data = models.JSONField(default=dict)  # snapshot of cart items
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    items_count = models.PositiveIntegerField(default=0)
    is_recovered = models.BooleanField(default=False)
    recovery_email_sent = models.BooleanField(default=False)
    recovery_email_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["email", "is_recovered", "recovery_email_sent"]),
            models.Index(fields=["created_at", "recovery_email_sent"]),
        ]

    def __str__(self):
        return f"AbandonedCart({self.email}) · {self.subtotal}"


class Notification(models.Model):
    """In-app notification for customers and staff."""

    class Type(models.TextChoices):
        ORDER = "order", _("Order update")
        PAYMENT = "payment", _("Payment")
        PROMO = "promo", _("Promotion")
        STOCK = "stock", _("Stock alert")
        REVIEW = "review", _("Review")
        SYSTEM = "system", _("System")
        WISHLIST = "wishlist", _("Wishlist")

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(
        max_length=20, choices=Type.choices, default=Type.SYSTEM, db_index=True
    )
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)

    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["user", "is_read", "-created_at"])]

    def __str__(self):
        return f"{self.user} · {self.title}"


class NewsletterSubscriber(models.Model):
    """Newsletter signup from the storefront footer/homepage."""

    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=100, default="website")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.email


class Setting(models.Model):
    """Key/value store powering /management/settings/."""

    key = models.CharField(max_length=100, unique=True)
    label = models.CharField(max_length=200)
    value = models.TextField(blank=True)
    group = models.CharField(max_length=50, default="general")
    help_text = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("group", "key")

    def __str__(self):
        return self.label

    @classmethod
    def get(cls, key, default=""):
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def set(cls, key, value, label=None, group="general", help_text=""):
        obj, _ = cls.objects.get_or_create(
            key=key, defaults={"label": label or key, "group": group}
        )
        obj.value = str(value)
        if label:
            obj.label = label
        if help_text:
            obj.help_text = help_text
        obj.save()
        return obj
