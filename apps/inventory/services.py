"""Inventory service — the only place that mutates stock levels."""
import logging

from django.db import transaction
from django.db.models import F
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


class StockError(Exception):
    """Raised for invalid inventory operations (message is user-facing)."""


def _get_targets(product_id, variant_id, for_update=True):
    from apps.catalog.models import Product, ProductVariant

    products = Product.objects.all()
    variants = ProductVariant.objects.all()
    if for_update:
        products = products.select_for_update()
        variants = variants.select_for_update()
    product = products.filter(pk=product_id).first()
    if product is None:
        raise StockError(_("Product not found."))
    variant = None
    if variant_id:
        variant = variants.filter(pk=variant_id, product=product).first()
        if variant is None:
            raise StockError(_("Product option not found."))
    return product, variant


def _record(product, variant, quantity, stock_after, transaction_type,
            reference="", note="", actor=None):
    from .models import StockTransaction

    StockTransaction.objects.create(
        product=product,
        variant=variant,
        transaction_type=transaction_type,
        quantity=quantity,
        stock_after=max(int(stock_after), 0),
        reference=reference,
        note=note,
        created_by=actor,
    )


def recalculate_product_stock(product):
    """Keep the denormalized product total in sync with its variants."""
    if product.variants.exists():
        total = sum(v.stock_quantity for v in product.variants.all())
        if product.stock_quantity != total:
            Product = type(product)
            Product.objects.filter(pk=product.pk).update(stock_quantity=total)
            product.stock_quantity = total


@transaction.atomic
def deduct_stock(product_id, variant_id=None, quantity=1, reference="",
                 transaction_type="sale", note="", actor=None):
    """Remove stock (used when an order is placed). Never goes negative."""
    product, variant = _get_targets(product_id, variant_id)
    quantity = int(quantity)
    if quantity <= 0:
        raise StockError(_("Quantity must be positive."))

    if variant is not None:
        if variant.stock_quantity < quantity:
            raise StockError(
                _("Not enough stock for “%(name)s” (%(n)s available).")
                % {"name": product.name, "n": variant.stock_quantity}
            )
        variant.stock_quantity -= quantity
        variant.save(update_fields=["stock_quantity"])
        product.stock_quantity = max(
            product.stock_quantity - quantity, 0
        )
        product.save(update_fields=["stock_quantity"])
        _record(product, variant, -quantity, variant.stock_quantity,
                transaction_type, reference, note, actor)
    else:
        if product.stock_quantity < quantity:
            raise StockError(
                _("Not enough stock for “%(name)s” (%(n)s available).")
                % {"name": product.name, "n": product.stock_quantity}
            )
        product.stock_quantity -= quantity
        product.save(update_fields=["stock_quantity"])
        _record(product, None, -quantity, product.stock_quantity,
                transaction_type, reference, note, actor)

    _check_low_stock(product)
    return True


# Backwards-friendly alias used by the order service.
reserve_stock = deduct_stock


@transaction.atomic
def restock(product_id, variant_id=None, quantity=1, reference="",
            transaction_type="return", note="", actor=None):
    """Add stock back (cancellations, returns, manual restock)."""
    product, variant = _get_targets(product_id, variant_id)
    quantity = int(quantity)
    if quantity <= 0:
        raise StockError(_("Quantity must be positive."))

    if variant is not None:
        variant.stock_quantity += quantity
        variant.save(update_fields=["stock_quantity"])
        product.stock_quantity += quantity
        product.save(update_fields=["stock_quantity"])
        _record(product, variant, quantity, variant.stock_quantity,
                transaction_type, reference, note, actor)
    else:
        product.stock_quantity += quantity
        product.save(update_fields=["stock_quantity"])
        _record(product, None, quantity, product.stock_quantity,
                transaction_type, reference, note, actor)
    return True


release_stock = restock


@transaction.atomic
def adjust_stock(product_id, variant_id, quantity, adjustment_type,
                 note="", actor=None):
    """Manual stock adjustment from the management portal.

    ``quantity`` is a signed integer (positive adds stock, negative removes).
    """
    from .models import StockTransaction

    if adjustment_type not in dict(StockTransaction.Type.choices):
        raise StockError(_("Invalid adjustment type."))
    if quantity > 0:
        return restock(product_id, variant_id, quantity, "manual",
                       "adjustment", note, actor)
    if quantity < 0:
        return deduct_stock(product_id, variant_id, abs(quantity), "manual",
                            "adjustment", note, actor)
    raise StockError(_("Adjustment quantity cannot be zero."))


def _check_low_stock(product):
    """Notify admins when a product drops to/below its minimum level."""
    try:
        if product.stock_quantity > product.min_stock_level:
            return
        from django.contrib.contenttypes.models import ContentType

        from apps.notifications.email import send_low_stock_email
        from apps.notifications.models import Notification
        from apps.notifications.models import Setting

        threshold = Setting.get("low_stock_threshold")
        try:
            min_level = int(threshold) if threshold else product.min_stock_level
        except ValueError:
            min_level = product.min_stock_level
        if product.stock_quantity > min_level:
            return

        from django.contrib.auth import get_user_model

        User = get_user_model()
        ct = ContentType.objects.get_for_model(type(product))
        admins = User.objects.filter(
            role__in=[User.Role.ADMIN, User.Role.STAFF], is_active=True
        )
        for admin in admins:
            Notification.objects.get_or_create(
                user=admin,
                type=Notification.Type.STOCK,
                title=_("Low stock: %(name)s") % {"name": product.name},
                defaults={
                    "body": _("Only %(count)s left (threshold %(threshold)s).")
                            % {"count": product.stock_quantity,
                               "threshold": min_level},
                    "link": f"/management/inventory/?q={product.sku}",
                    "content_type": ct,
                    "object_id": product.pk,
                },
            )
        if product.stock_quantity == 0:
            send_low_stock_email(product, min_level)
    except Exception:  # pragma: no cover - never break the main flow
        logger.exception("Low stock notification failed for %s", product.sku)
