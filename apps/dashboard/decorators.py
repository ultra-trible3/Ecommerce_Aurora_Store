"""Access control helpers for the management portal."""
from functools import wraps

from django.contrib.auth import REDIRECT_FIELD_NAME
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext as _


def management_required(view_func):
    """Allow only active staff/superuser accounts into /management/."""

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            login_url = reverse("accounts:login")
            next_url = request.get_full_path()
            return redirect(f"{login_url}?{REDIRECT_FIELD_NAME}={next_url}")
        if not user.is_management:
            raise PermissionDenied(
                _("The management portal is limited to staff accounts.")
            )
        return view_func(request, *args, **kwargs)

    return _wrapped


def permission_required(*perms, admin_ok=True):
    """Require one of the given Django permissions (superusers always pass)."""

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if admin_ok and user.is_superuser:
                return view_func(request, *args, **kwargs)
            if perms and not user.has_perms(perms):
                raise PermissionDenied(
                    _("You do not have permission to perform this action.")
                )
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
