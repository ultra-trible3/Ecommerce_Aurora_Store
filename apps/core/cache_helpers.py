"""Small cached read-models used by template context processors."""
from django.core.cache import cache

NAV_CATEGORIES_CACHE_KEY = "nav_categories"
NAV_CATEGORIES_TTL = 60 * 10  # 10 minutes


def get_nav_categories():
    """Top-level categories with children prefetched (cached)."""
    cached = cache.get(NAV_CATEGORIES_CACHE_KEY)
    if cached is not None:
        return cached

    from django.db.models import Prefetch

    from apps.catalog.models import Category

    children = Category.objects.filter(is_active=True).order_by("position", "name")
    categories = list(
        Category.objects.filter(is_active=True, parent__isnull=True)
        .prefetch_related(Prefetch("children", queryset=children))
        .order_by("position", "name")
    )
    cache.set(NAV_CATEGORIES_CACHE_KEY, categories, NAV_CATEGORIES_TTL)
    return categories


def invalidate_nav_categories():
    """Drop the cached category navigation."""
    cache.delete(NAV_CATEGORIES_CACHE_KEY)
