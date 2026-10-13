"""Inventory: stock transactions (ledger) and stock service helpers."""
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class StockTransaction(TimeStampedModel):
    """Immutable ledger of every stock movement."""

    class Type(models.TextChoices):
        PURCHASE = "purchase", _("Purchase")
        SALE = "sale", _("Sale")
        RETURN = "return", _("Return")
        ADJUSTMENT = "adjustment", _("Manual adjustment")
        CANCELLATION = "cancellation", _("Cancellation")
        RESTOCK = "restock", _("Restock")

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="stock_transactions",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="stock_transactions",
    )
    transaction_type = models.CharField(
        max_length=20, choices=Type.choices, db_index=True
    )
    quantity = models.IntegerField(
        help_text=_("Positive = incoming, negative = outgoing")
    )
    stock_after = models.PositiveIntegerField(default=0)
    reference = models.CharField(max_length=100, blank=True, db_index=True)
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_transactions",
    )

    class Meta:
        verbose_name = _("stock transaction")
        verbose_name_plural = _("stock transactions")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["product", "-created_at"]),
            models.Index(fields=["transaction_type", "-created_at"]),
        ]

    def __str__(self):
        sign = "+" if self.quantity >= 0 else ""
        return (
            f"{self.transaction_type}: {sign}{self.quantity} "
            f"of {self.product.name}"
        )
