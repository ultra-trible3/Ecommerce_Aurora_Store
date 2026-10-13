from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import Address, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "username", "role", "is_staff", "is_active",
                    "email_verified", "date_joined")
    list_filter = ("role", "is_staff", "is_superuser", "is_active",
                   "email_verified")
    search_fields = ("email", "username", "first_name", "last_name", "phone")
    readonly_fields = ("last_login", "date_joined")
    fieldsets = DjangoUserAdmin.fieldsets + (
        (_("Store profile"), {
            "fields": ("phone", "role", "email_verified", "date_of_birth",
                       "profile_image"),
        }),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "username", "password1", "password2"),
        }),
    )


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "city", "country", "address_type",
                    "is_default")
    list_filter = ("address_type", "country", "is_default")
    search_fields = ("full_name", "user__email", "city", "postal_code")
    list_select_related = ("user",)
