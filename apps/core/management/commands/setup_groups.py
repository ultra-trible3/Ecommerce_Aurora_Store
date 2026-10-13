"""Setup management portal groups with proper permissions."""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction


GROUP_PERMISSIONS = {
    "Admin": [
        "view_order", "add_order", "change_order", "delete_order",
        "view_orderitem", "add_orderitem", "change_orderitem", "delete_orderitem",
        "view_orderstatushistory", "add_orderstatushistory", "change_orderstatushistory", "delete_orderstatushistory",
        "view_product", "add_product", "change_product", "delete_product",
        "view_category", "add_category", "change_category", "delete_category",
        "view_brand", "add_brand", "change_brand", "delete_brand",
        "view_coupon", "add_coupon", "change_coupon", "delete_coupon",
        "view_review", "change_review",
        "view_user", "change_user", "delete_user",
        "view_stocktransaction", "change_stocktransaction",
        "view_newslettersubscriber", "change_newslettersubscriber",
        "view_notification", "change_notification",
        "change_setting",
        "view_banner", "add_banner", "change_banner", "delete_banner",
    ],
    "Order Manager": [
        "view_order", "add_order", "change_order", "delete_order",
        "view_orderitem", "add_orderitem", "change_orderitem", "delete_orderitem",
        "view_orderstatushistory", "add_orderstatushistory", "change_orderstatushistory", "delete_orderstatushistory",
        "view_coupon", "add_coupon", "change_coupon", "delete_coupon",
        "view_user", "change_user",
        "view_banner", "add_banner", "change_banner", "delete_banner",
    ],
    "Support Agent": [
        "view_order", "change_order",
        "view_orderitem",
        "view_orderstatushistory", "add_orderstatushistory", "change_orderstatushistory",
        "view_review", "change_review",
        "view_user", "change_user",
        "view_notification", "change_notification",
        "view_banner", "add_banner", "change_banner", "delete_banner",
    ],
    "Content Manager": [
        "view_product", "add_product", "change_product", "delete_product",
        "view_category", "add_category", "change_category", "delete_category",
        "view_brand", "add_brand", "change_brand", "delete_brand",
        "view_review", "change_review",
        "view_newslettersubscriber", "change_newslettersubscriber",
        "view_banner", "add_banner", "change_banner", "delete_banner",
    ],
    "Inventory Manager": [
        "view_order", "view_orderitem",
        "view_product", "change_product",
        "view_category", "view_brand",
        "view_stocktransaction", "change_stocktransaction",
        "view_banner", "change_banner",
    ],
}


class Command(BaseCommand):
    help = "Create or update management portal groups with proper permissions."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Remove existing groups and recreate")

    def handle(self, *args, **options):
        if options["reset"]:
            Group.objects.filter(name__in=GROUP_PERMISSIONS.keys()).delete()
            self.stdout.write("Removed existing groups.")

        with transaction.atomic():
            for group_name, perm_codenames in GROUP_PERMISSIONS.items():
                group, created = Group.objects.get_or_create(name=group_name)
                if created:
                    self.stdout.write(f"Created group: {group_name}")
                else:
                    self.stdout.write(f"Updating group: {group_name}")

                # Clear and set permissions
                perms = Permission.objects.filter(codename__in=perm_codenames)
                found = list(perms.values_list("codename", flat=True))
                missing = set(perm_codenames) - set(found)
                if missing:
                    self.stdout.write(self.style.WARNING(
                        f"  Missing permissions (not found): {', '.join(missing)}"
                    ))
                group.permissions.set(perms)
                self.stdout.write(f"  Set {perms.count()} permissions")

        self.stdout.write(self.style.SUCCESS("Groups configured successfully."))