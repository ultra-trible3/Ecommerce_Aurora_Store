from django.contrib import admin

from .models import StockTransaction


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "product", "variant", "transaction_type",
                    "quantity", "stock_after", "created_by")
    list_filter = ("transaction_type", "created_at")
    search_fields = ("product__name", "product__sku", "variant__name",
                     "reference", "note")
    list_select_related = ("product", "variant", "created_by")
    readonly_fields = ("created_at", "updated_at")

    def has_change_permission(self, request, obj=None):
        return False
