"""Product reviews and ratings."""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.core.validators import validate_image_file


class Review(TimeStampedModel):
    """A customer review of a product (moderated before publishing)."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending review")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="reviews"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField(default=5)
    title = models.CharField(max_length=200, blank=True)
    body = models.TextField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    is_verified_purchase = models.BooleanField(default=False)
    admin_reply = models.TextField(blank=True)

    class Meta:
        ordering = ("-created_at",)
        unique_together = ("product", "user")
        indexes = [
            models.Index(fields=["product", "status", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return _("%(product)s – %(rating)s★ by %(user)s") % {
            "product": self.product,
            "rating": self.rating,
            "user": self.user,
        }

    @property
    def stars(self):
        return range(1, 6)

    @property
    def is_approved(self):
        return self.status == self.Status.APPROVED


class ReviewImage(models.Model):
    """Optional photo attached to a review."""

    review = models.ForeignKey(
        Review, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(
        upload_to="reviews/%Y/%m/", validators=[validate_image_file]
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return _("Image for review #%(pk)s") % {"pk": self.pk}


class ProductQuestion(TimeStampedModel):
    """A customer question about a product (moderated before publishing)."""

    class Status(models.TextChoices):
        PENDING = "pending", _("Pending review")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="questions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_questions",
    )
    # Guests may ask with just a name/email so we can notify them of the reply.
    asker_name = models.CharField(max_length=150, blank=True)
    asker_email = models.EmailField(blank=True)
    body = models.TextField()
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["product", "status", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return _("Q#%(pk)s · %(body)s") % {"pk": self.pk, "body": self.body[:40]}

    @property
    def display_name(self):
        if self.user_id:
            return self.user.get_full_name() or self.user.username
        return self.asker_name or str(_("Guest"))

    @property
    def is_approved(self):
        return self.status == self.Status.APPROVED

    @property
    def approved_answers(self):
        return self.answers.filter(
            status=ProductAnswer.Status.APPROVED
        ).select_related("user")

    @property
    def has_approved_answer(self):
        return self.answers.filter(
            status=ProductAnswer.Status.APPROVED
        ).exists()


class ProductAnswer(TimeStampedModel):
    """An answer to a product question (published by staff, or moderated)."""

    question = models.ForeignKey(
        ProductQuestion, on_delete=models.CASCADE, related_name="answers"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_answers",
    )
    body = models.TextField()
    is_staff_answer = models.BooleanField(default=False)
    status = models.CharField(
        max_length=10,
        choices=ProductQuestion.Status.choices,
        default=ProductQuestion.Status.APPROVED,
        db_index=True,
    )

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return _("A#%(pk)s for question #%(qid)s") % {
            "pk": self.pk,
            "qid": self.question_id,
        }

    @property
    def display_name(self):
        if self.is_staff_answer:
            from django.conf import settings as dj_settings

            return dj_settings.SITE_NAME
        if self.user_id:
            return self.user.get_full_name() or self.user.username
        return str(_("Customer"))
