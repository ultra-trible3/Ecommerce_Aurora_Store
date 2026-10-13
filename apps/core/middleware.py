"""Custom middleware."""
import logging
import time
import uuid
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import logout
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin
from django.utils.translation import gettext as _


logger = logging.getLogger(__name__)


class RateLimitMiddleware(MiddlewareMixin):
    """Simple IP-based rate limiting using cache."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, "RATELIMIT_ENABLE", True)
        self.requests_per_minute = getattr(settings, "RATELIMIT_REQUESTS_PER_MINUTE", 60)
        self.requests_per_hour = getattr(settings, "RATELIMIT_REQUESTS_PER_HOUR", 1000)
        super().__init__(get_response)

    def _get_client_ip(self, request):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")

    def _is_rate_limited(self, ip, limit, window_seconds, suffix):
        key = f"ratelimit:{suffix}:{ip}"
        current = cache.get(key, 0)
        if current >= limit:
            return True
        cache.set(key, current + 1, window_seconds)
        return False

    def process_request(self, request):
        if not self.enabled:
            return None

        # Skip rate limiting for health checks and static files
        if request.path in ("/health/", "/healthz/") or request.path.startswith("/static/"):
            return None

        ip = self._get_client_ip(request)

        # Per-minute limit
        if self._is_rate_limited(ip, self.requests_per_minute, 60, "minute"):
            logger.warning(f"Rate limit exceeded (minute) for IP: {ip}")
            return HttpResponse(
                _("Rate limit exceeded. Please slow down."),
                status=429,
                content_type="text/plain",
            )

        # Per-hour limit
        if self._is_rate_limited(ip, self.requests_per_hour, 3600, "hour"):
            logger.warning(f"Rate limit exceeded (hour) for IP: {ip}")
            return HttpResponse(
                _("Hourly rate limit exceeded. Please try again later."),
                status=429,
                content_type="text/plain",
            )

        return None


def _build_csp_header(request):
    """Build Content-Security-Policy header."""
    csp_directives = [
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://fonts.googleapis.com https://fonts.gstatic.com https://js.stripe.com https://www.paypal.com https://www.paypalobjects.com",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com",
        "font-src 'self' data: https://fonts.googleapis.com https://fonts.gstatic.com",
        # blob: lets the browser preview locally picked files (avatar crop).
        "img-src 'self' data: blob: https:",
        "connect-src 'self' blob: https://api.stripe.com https://www.paypal.com https://api-m.paypal.com https://api-m.sandbox.paypal.com",
        "frame-src 'self' https://js.stripe.com https://www.paypal.com https://www.sandbox.paypal.com",
        "form-action 'self'",
        "base-uri 'self'",
        "object-src 'none'",
    ]
    if settings.DEBUG:
        csp_directives.append("script-src-elem 'self' 'unsafe-inline' 'unsafe-eval'")
    return "; ".join(csp_directives)


class SecurityHeadersMiddleware(MiddlewareMixin):
    """Add security-related response headers."""

    def process_response(self, request, response):
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("X-Frame-Options", settings.X_FRAME_OPTIONS)
        response.setdefault("Referrer-Policy", settings.SECURE_REFERRER_POLICY)
        response.setdefault("Content-Security-Policy", _build_csp_header(request))
        
        if not settings.DEBUG:
            response.setdefault(
                "Permissions-Policy",
                "geolocation=(), microphone=(), camera=(), payment=(self \"https://js.stripe.com\" \"https://www.paypal.com\")",
            )
            response.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains; preload")
            response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
            response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        
        return response


class CartSessionMiddleware(MiddlewareMixin):
    """Ensure anonymous sessions get a stable cart key early.

    The cart key is created lazily by the cart app when needed; this
    middleware only marks the session so context processors can short-circuit.
    """

    def process_request(self, request):
        if not request.session.session_key:
            # Do not create a session for every anonymous visitor, only
            # remember whether the user is authenticated.
            pass
        return None


class RequestLoggingMiddleware(MiddlewareMixin):
    """Write one access-log line per successful request.

    Only the URL *path* is logged -- never the query string, headers, cookies
    or body -- so tokens and other secrets can never leak into the log files.
    Error responses (4xx/5xx) are intentionally left to Django's built-in
    ``django.request`` logger, which adds the full traceback, so they are never
    logged twice.
    """

    logger = logging.getLogger("apps.core.requests")

    # Same noise-reduction rules as the rate limiter.
    SKIP_PREFIXES = ("/static/", "/media/", "/health/", "/healthz/")

    def process_request(self, request):
        request._request_started_at = time.perf_counter()
        return None

    def process_response(self, request, response):
        try:
            status = response.status_code
            if status >= 400 or request.path.startswith(self.SKIP_PREFIXES):
                return response

            started = getattr(request, "_request_started_at", None)
            duration_ms = (
                (time.perf_counter() - started) * 1000 if started is not None else None
            )

            user = getattr(request, "user", None)
            actor = user.pk if user is not None and user.is_authenticated else "-"

            if duration_ms is None:
                self.logger.info(
                    "%s %s -> %s user=%s", request.method, request.path, status, actor
                )
            else:
                self.logger.info(
                    "%s %s -> %s (%.1f ms) user=%s",
                    request.method,
                    request.path,
                    status,
                    duration_ms,
                    actor,
                )
        except Exception:  # pragma: no cover - logging must never break a response
            return response

        return response


class SingleDeviceSessionMiddleware:
    """Enforce a single active device/session per authenticated user.

    Each browser is tagged with a persistent ``device_id`` cookie (generated
    here on first contact). On every login, ``apps.accounts.signals`` records
    the new session key as the only one allowed to stay signed in; this
    middleware signs out any other browser whose session key no longer matches,
    so logging in on a second device kicks the first.

    Must run after ``AuthenticationMiddleware`` (which sets ``request.user``)
    and before the view, so the rogue session never reaches the page.
    """

    DEVICE_COOKIE = "device_id"
    DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # one year

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        device_id = request.COOKIES.get(self.DEVICE_COOKIE) or uuid.uuid4().hex
        request.device_id = device_id

        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and user.active_session_key
            and request.session.session_key != user.active_session_key
        ):
            logout(request)
            response = self._kicked_response(request)
        else:
            response = self.get_response(request)

        if request.COOKIES.get(self.DEVICE_COOKIE) != device_id:
            response.set_cookie(
                self.DEVICE_COOKIE,
                device_id,
                max_age=self.DEVICE_COOKIE_MAX_AGE,
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG,
            )
        return response

    @staticmethod
    def _kicked_response(request):
        """Tell a kicked browser it was signed in elsewhere.

        AJAX callers get JSON (the existing fragments already understand
        ``authenticated: false``); a normal navigation is redirected to the
        login page. Both carry a short-lived marker cookie so the login page
        can still explain *why* even when the kick is noticed on a later
        request (e.g. a background tracking beacon consumed it first).
        """
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            response = JsonResponse({"authenticated": False, "session_kicked": True})
        else:
            login_url = reverse("accounts:login")
            target = quote(request.get_full_path(), safe="")
            response = redirect(f"{login_url}?kicked=1&next={target}")

        response.set_cookie(
            "au_kicked",
            "1",
            max_age=300,
            httponly=True,
            samesite="Lax",
            secure=not settings.DEBUG,
        )
        return response
