from django.contrib import admin

from .models import NewsletterSubscriber, Notification, Setting


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "title", "is_read", "created_at")
    list_filter = ("type", "is_read", "created_at")
    search_fields = ("title", "body", "user__email", "link")
    list_select_related = ("user",)
    date_hierarchy = "created_at"


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "is_active", "source", "created_at")
    list_filter = ("is_active", "source", "created_at")
    search_fields = ("email",)
    list_editable = ("is_active",)


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "group", "updated_at")
    list_filter = ("group",)
    search_fields = ("key", "label", "value")
    readonly_fields = ("updated_at",)
