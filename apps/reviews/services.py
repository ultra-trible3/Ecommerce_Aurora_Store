"""Review helpers: keep denormalized product rating in sync."""
from django.db.models import Avg, Count, Q


def refresh_product_rating(product):
    """Recompute ``rating_average``/``rating_count`` from approved reviews."""
    stats = product.reviews.filter(status="approved").aggregate(
        avg=Avg("rating"), count=Count("id")
    )
    product.rating_average = round(stats["avg"] or 0, 2)
    product.rating_count = stats["count"] or 0
    product.save(update_fields=["rating_average", "rating_count"])
    return product


def refresh_all_ratings():
    """Recompute ratings for every product (management command helper)."""
    from apps.catalog.models import Product

    for product in Product.objects.all():
        refresh_product_rating(product)
