"""Template context processors for catalog."""
from apps.catalog.brand_logos import get_brand_logos
from apps.catalog.deals import DEALS
from apps.catalog.services import get_recently_viewed_products


def recently_viewed_products(request):
    """Provide recently viewed products for the storefront."""
    return {"recently_viewed_products": get_recently_viewed_products(request, limit=4)}


def logo_marquee(request):
    """Default logo list for the reusable LogoMarquee component.

    Prefers the dashboard-editable ``marquee_logos`` setting and falls back to
    the bundled ``BRAND_LOGOS`` list when it is not configured.
    """
    return {"marquee_logos": get_brand_logos()}


def deals_mosaic(request):
    """Promotional tiles for the homepage Deals & Promotions mosaic."""
    return {"home_deals": DEALS}