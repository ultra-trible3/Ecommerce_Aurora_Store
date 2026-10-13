"""Authentication signals: bind each login to a single active session.

When a user signs in, the freshly rotated session key becomes the *only*
session allowed to stay authenticated. Any browser still holding an older
session is signed out by ``apps.core.middleware.SingleDeviceSessionMiddleware``.

Using Django's ``user_logged_in`` signal means every login path is covered in
one place: the account login view, registration/email-verification auto-login,
the management portal and the Django admin.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

User = get_user_model()


@receiver(user_logged_in)
def bind_active_session(sender, request, user, **kwargs):
    """Record the session key that is allowed to remain signed in."""
    session = getattr(request, "session", None)
    if session is None:
        return

    # ``auth.login()`` rotates the session key before emitting this signal, so
    # the value below is the new, canonical key for this browser.
    session_key = session.session_key or ""
    if not session_key:
        return

    device_id = getattr(request, "device_id", "") or ""

    # Keep the in-memory instance in sync for the rest of this request, then
    # persist with ``update()`` so custom ``User.save()`` side effects (staff
    # flag, username generation) are not re-triggered.
    user.active_session_key = session_key
    user.active_device_id = device_id
    User.objects.filter(pk=user.pk).update(
        active_session_key=session_key,
        active_device_id=device_id,
    )
