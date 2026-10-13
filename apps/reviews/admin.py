from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Review, ReviewImage


class ReviewImageInline(admin.TabularInline):
    model = ReviewImage
    extra = 1


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "rating", "user", "status",
                    "is_verified_purchase", "created_at")
    list_filter = ("status", "rating", "is_verified_purchase", "created_at")
    search_fields = ("title", "body", "product__name", "user__email",
                     "admin_reply")
    list_select_related = ("product", "user")
    inlines = (ReviewImageInline,)
    readonly_fields = ("created_at", "updated_at")
    actions = ("approve_selected", "reject_selected")
    fieldsets = (
        (None, {"fields": ("product", "user", "rating", "status",
                           "is_verified_purchase")}),
        (_("Review"), {"fields": ("title", "body", "admin_reply")}),
        (_("Timestamps"), {"fields": ("created_at", "updated_at")}),
    )

    @admin.action(description=_("Approve selected reviews"))
    def approve_selected(self, request, queryset):
        updated = queryset.update(status=Review.Status.APPROVED)
        self.message_user(request, _("%(n)s review(s) approved.") % {"n": updated})

    @admin.action(description=_("Reject selected reviews"))
    def reject_selected(self, request, queryset):
        updated = queryset.update(status=Review.Status.REJECTED)
        self.message_user(request, _("%(n)s review(s) rejected.") % {"n": updated})
