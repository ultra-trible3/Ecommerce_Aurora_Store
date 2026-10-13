"""Dashboard-only context values (sidebar badges)."""


def portal_context(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated or not user.is_management:
        return {}

    try:
        from apps.notifications.models import Notification
        from apps.reviews.models import Review

        return {
            "pending_review_count": Review.objects.filter(
                status=Review.Status.PENDING
            ).count(),
            "portal_unread": Notification.objects.filter(
                user=user, is_read=False
            ).count(),
        }
    except Exception:  # pragma: no cover
        return {}
