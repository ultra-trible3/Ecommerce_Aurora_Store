"""Custom user model and addresses."""
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.validators import validate_image_file, validate_phone


class User(AbstractUser):
    """Custom user with email as the login identifier and role support."""

    class Role(models.TextChoices):
        CUSTOMER = "customer", _("Customer")
        STAFF = "staff", _("Staff")
        ADMIN = "admin", _("Admin")

    email = models.EmailField(_("Email address"), unique=True)
    username = models.CharField(
        max_length=150,
        unique=True,
        blank=True,
        help_text=_("Optional. Generated from your email if left blank."),
    )
    phone = models.CharField(
        max_length=30, blank=True, validators=[validate_phone]
    )
    profile_image = models.ImageField(
        upload_to="avatars/%Y/%m/", blank=True, validators=[validate_image_file]
    )
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True
    )
    email_verified = models.BooleanField(default=False)
    verification_token = models.CharField(
        max_length=64, blank=True, null=True, default=None, db_index=True
    )
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    # Single-device login: the one session key that is allowed to stay signed
    # in, plus the browser id it belongs to. Overwritten on every login (see
    # ``apps.accounts.signals`` / ``apps.core.middleware``).
    active_session_key = models.CharField(
        max_length=40, blank=True, default="", db_index=True
    )
    active_device_id = models.CharField(max_length=64, blank=True, default="")

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        indexes = [models.Index(fields=["email"])]

    def __str__(self):
        return self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        if not self.username:
            base = (self.email.split("@")[0] if self.email else "user")[:140]
            username = base
            counter = 1
            qs = User.objects.exclude(pk=self.pk)
            while qs.filter(username=username).exists():
                counter += 1
                username = f"{base}{counter}"
            self.username = username
        if self.role in (self.Role.STAFF, self.Role.ADMIN) and not self.is_staff:
            self.is_staff = True
        if self.role == self.Role.ADMIN:
            self.is_superuser = True
        super().save(*args, **kwargs)

    @property
    def is_admin(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def is_management(self):
        """True for users allowed to access the management portal."""
        return self.is_active and (self.is_staff or self.is_superuser)

    @property
    def initials(self):
        """Two-character avatar fallback: initials of the first two words of
        the display name, or the first two characters when it's a single word."""
        name = self.get_full_name() or self.username or self.email
        parts = [p for p in name.split() if p]
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        base = (parts[0] if parts else name).strip()
        return (base[:2] or "U").upper()

    def generate_verification_token(self):
        """Create a fresh email verification token."""
        import secrets

        self.verification_token = secrets.token_urlsafe(32)
        self.email_verification_sent_at = timezone.now()
        return self.verification_token


class Address(TimeStampedModel):
    """A saved shipping/billing address belonging to a user."""

    class Type(models.TextChoices):
        SHIPPING = "shipping", _("Shipping")
        BILLING = "billing", _("Billing")

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="addresses"
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, validators=[validate_phone])
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, default=_("United States"))
    postal_code = models.CharField(max_length=20)
    address_type = models.CharField(
        max_length=10, choices=Type.choices, default=Type.SHIPPING, db_index=True
    )
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        ordering = ("-is_default", "-updated_at")
        indexes = [models.Index(fields=["user", "address_type"])]

    def __str__(self):
        return f"{self.full_name} – {self.city}"

    @property
    def as_line(self):
        parts = [self.address_line1, self.address_line2, self.city, self.state,
                 self.postal_code, self.country]
        return ", ".join(p for p in parts if p)

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(
                user=self.user, address_type=self.address_type
            ).exclude(pk=self.pk).update(is_default=False)
        elif not Address.objects.filter(
            user=self.user, address_type=self.address_type
        ).exclude(pk=self.pk).exists():
            self.is_default = True
        super().save(*args, **kwargs)
