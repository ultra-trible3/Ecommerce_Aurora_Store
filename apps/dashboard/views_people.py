"""People: customers, newsletter subscribers and staff notifications."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.core.utils import paginate
from apps.notifications.models import Notification, NewsletterSubscriber
from apps.orders.models import Order
from .decorators import management_required, permission_required
from .forms import CustomerEditForm

User = get_user_model()


@management_required
@permission_required("accounts.view_user")
def customers(request):
    # Staff accounts default to the customer role: keep them out of the
    # customer management UI entirely.
    base_qs = User.objects.filter(
        role=User.Role.CUSTOMER, is_staff=False
    )
    qs = base_qs.order_by("-date_joined")
    q = (request.GET.get("q") or "").strip()
    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(email__icontains=q)
            | Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(username__icontains=q)
        )

    page_obj = paginate(request, qs, per_page=20)
    rows = []
    for customer in page_obj.object_list:
        rows.append({
            "obj": customer,
            "order_count": Order.objects.filter(user=customer).count(),
            "spent": sum(
                o.total
                for o in Order.objects.filter(user=customer).exclude(
                    status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED]
                )
            ),
        })
    return render(
        request,
        "management/customers/list.html",
        {
            "nav": "customers",
            "page_obj": page_obj,
            "rows": rows,
            "q": q,
            "total": base_qs.count(),
        },
    )


@management_required
@permission_required("accounts.view_user")
def customer_detail(request, pk):
    customer = get_object_or_404(User, pk=pk, role=User.Role.CUSTOMER)
    orders = Order.objects.filter(user=customer).order_by("-created_at")
    context = {
        "nav": "customers",
        "customer": customer,
        "orders": orders,
        "order_count": orders.count(),
        "spent": sum(
            o.total
            for o in orders.exclude(
                status__in=[Order.Status.CANCELLED, Order.Status.REFUNDED]
            )
        ),
        "addresses": customer.addresses.all(),
        "reviews": customer.reviews.select_related("product")[:10],
    }
    return render(request, "management/customers/detail.html", context)


@management_required
@require_POST
def customer_toggle(request, pk):
    customer = get_object_or_404(User, pk=pk, role=User.Role.CUSTOMER)
    customer.is_active = not customer.is_active
    customer.save(update_fields=["is_active"])
    messages.success(
        request,
        _("%(email)s %(state)s.")
        % {
            "email": customer.email,
            "state": _("reactivated") if customer.is_active else _("deactivated"),
        },
    )
    return redirect("dashboard:customer_detail", pk=customer.pk)


@management_required
@permission_required("accounts.change_user")
@require_http_methods(["GET", "POST"])
def customer_edit(request, pk):
    customer = get_object_or_404(User, pk=pk, role=User.Role.CUSTOMER)
    form = CustomerEditForm(request.POST or None, instance=customer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request, _("%(email)s updated.") % {"email": customer.email}
        )
        return redirect("dashboard:customer_detail", pk=customer.pk)
    return render(
        request,
        "management/customers/form.html",
        {"nav": "customers", "customer": customer, "form": form},
    )


@management_required
@permission_required("accounts.delete_user")
@require_POST
def customer_delete(request, pk):
    customer = get_object_or_404(User, pk=pk, role=User.Role.CUSTOMER)
    if customer.pk == request.user.pk:
        messages.error(request, _("You cannot delete your own account."))
        return redirect("dashboard:customer_detail", pk=customer.pk)
    if customer.is_staff or customer.is_superuser:
        messages.error(
            request,
            _("Staff accounts cannot be deleted from the customers area."),
        )
        return redirect("dashboard:customer_detail", pk=customer.pk)

    email = customer.email
    order_count = Order.objects.filter(user=customer).count()
    customer.delete()
    if order_count:
        messages.success(
            request,
            _(
                "%(email)s deleted. Their %(count)s order(s) were kept on "
                "record."
            )
            % {"email": email, "count": order_count},
        )
    else:
        messages.success(
            request, _("%(email)s deleted.") % {"email": email}
        )
    return redirect("dashboard:customers")


# --------------------------------------------------------------------------
# Newsletter subscribers
# --------------------------------------------------------------------------
@management_required
@permission_required("notifications.view_newslettersubscriber")
def subscribers(request):
    qs = NewsletterSubscriber.objects.order_by("-created_at")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(email__icontains=q)
    page_obj = paginate(request, qs, per_page=25)
    return render(
        request,
        "management/subscribers.html",
        {
            "nav": "subscribers",
            "page_obj": page_obj,
            "subscribers": page_obj.object_list,
            "q": q,
            "active_count": NewsletterSubscriber.objects.filter(
                is_active=True
            ).count(),
        },
    )


@management_required
@require_POST
def subscriber_toggle(request, pk):
    subscriber = get_object_or_404(NewsletterSubscriber, pk=pk)
    subscriber.is_active = not subscriber.is_active
    subscriber.save(update_fields=["is_active"])
    return redirect("dashboard:subscribers")


# --------------------------------------------------------------------------
# Staff notifications
# --------------------------------------------------------------------------
@management_required
@permission_required("notifications.view_notification")
def notifications(request):
    qs = Notification.objects.filter(user=request.user).order_by("-created_at")
    show = request.GET.get("filter", "")
    if show == "unread":
        qs = qs.filter(is_read=False)
    page_obj = paginate(request, qs, per_page=25)
    return render(
        request,
        "management/notifications.html",
        {
            "nav": "notifications",
            "page_obj": page_obj,
            "notifications": page_obj.object_list,
            "filter": show,
            "unread_count": Notification.objects.filter(
                user=request.user, is_read=False
            ).count(),
        },
    )


@management_required
@require_POST
def notification_read(request, pk):
    Notification.objects.filter(pk=pk, user=request.user).update(is_read=True)
    return redirect("dashboard:notifications")


@management_required
@require_POST
def notification_read_all(request):
    Notification.objects.filter(user=request.user, is_read=False).update(
        is_read=True
    )
    messages.success(request, _("All notifications marked as read."))
    return redirect("dashboard:notifications")
