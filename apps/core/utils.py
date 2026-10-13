"""Core utility helpers."""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.cache import cache
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import QueryDict


def money(value):
    """Quantize a decimal value to 2 places using commercial rounding."""
    if value is None:
        return Decimal("0.00")
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def currency(value):
    """Format a decimal value as a currency string."""
    return f"{settings.CURRENCY_SYMBOL}{money(value):,.2f}"


def generate_order_number():
    """Generate a human friendly unique order number."""
    from django.utils import timezone

    from apps.orders.models import Order

    stamp = timezone.now().strftime("%Y%m%d")
    prefix = f"ORD-{stamp}-"
    last = (
        Order.objects.filter(order_number__startswith=prefix)
        .order_by("-order_number")
        .values_list("order_number", flat=True)
        .first()
    )
    sequence = 1
    if last:
        try:
            sequence = int(last.rsplit("-", 1)[-1]) + 1
        except (ValueError, IndexError):
            sequence = Order.objects.filter(
                order_number__startswith=prefix
            ).count() + 1
    return f"{prefix}{sequence:04d}"


def paginate(request, queryset, per_page=None, orphans=2):
    """Paginate ``queryset`` honoring ``?page=`` with graceful fallback."""
    per_page = per_page or getattr(settings, "DEFAULT_PAGINATION", 12)
    page = request.GET.get("page", 1)
    paginator = Paginator(queryset, per_page, orphans=orphans)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)
    return page_obj


def cleaned_querystring(request, exclude=("page",)):
    """Return the current querystring without the excluded keys."""
    q = QueryDict(request.META.get("QUERY_STRING", ""), mutable=True)
    for key in exclude:
        q.pop(key, None)
    return q.urlencode()


def throttle(key, limit=30, period=60):
    """Simple cache-based rate limiter.

    Returns True when the request is allowed, False when the limit for
    ``key`` within ``period`` seconds has been exceeded.
    """
    if not getattr(settings, "RATELIMIT_ENABLE", True):
        return True
    cache_key = f"throttle:{key}"
    data = cache.get(cache_key)
    if data is None:
        cache.set(cache_key, {"count": 1, "reset": period}, period)
        return True
    if data["count"] >= limit:
        return False
    data["count"] += 1
    cache.set(cache_key, data, period)
    return True


def client_ip(request):
    """Best-effort client IP extraction."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def unique_id(prefix="ID", length=8):
    """Generate a short random identifier."""
    import secrets
    import string

    alphabet = string.ascii_uppercase + string.digits
    token = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}-{token}"


def safe_next(request, default="/"):
    """Return a validated, same-host ``next`` target from GET or POST.

    Prevents open-redirect abuse (e.g. ``?next=https://evil.com`` or the
    protocol-relative ``?next=//evil.com``). Falls back to ``default`` whenever
    the supplied value is missing or points off-site.
    """
    from django.utils.http import url_has_allowed_host_and_scheme

    next_url = request.GET.get("next") or request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return default
