from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "provider", "status", "amount", "currency",
                    "transaction_id", "paid_at", "created_at")
    list_filter = ("provider", "status", "created_at")
    search_fields = ("transaction_id", "order__order_number", "order__email",
                     "error_message")
    list_select_related = ("order",)
    date_hierarchy = "created_at"
    readonly_fields = ("provider_payload", "client_secret", "webhook_received",
                       "paid_at", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("order", "provider", "status",
                           "created_at")}),
        (_("Money"), {"fields": ("amount", "currency", "paid_at")}),
        (_("Provider reference"), {
            "fields": ("transaction_id", "client_secret", "provider_payload",
                       "webhook_received", "error_message", "updated_at"),
        }),
    )
