"""Accounts app configuration: user groups and permissions bootstrap."""
from django.apps import AppConfig

# Standard model permission actions.
CRUD = ["view", "add", "change", "delete"]

GROUP_PERMISSIONS = {
    "Admin": "*",
    "Inventory Manager": {
        "catalog": {
            "product": CRUD,
            "productvariant": CRUD,
            "productimage": CRUD,
            "attribute": CRUD,
            "attributevalue": CRUD,
            "category": ["view"],
            "brand": ["view"],
        },
        "inventory": {"stocktransaction": CRUD},
        "orders": {"order": ["view"], "orderitem": ["view"]},
        "reviews": {"review": ["view"]},
        "notifications": {"setting": ["view"]},
    },
    "Order Manager": {
        "orders": {
            "order": CRUD,
            "orderitem": CRUD,
            "orderstatushistory": CRUD,
            "shippingmethod": CRUD,
            "couponredemption": ["view"],
        },
        "accounts": {"user": ["view"], "address": ["view"]},
        "payments": {"payment": ["view", "change"]},
        "coupons": {"coupon": ["view"]},
        "reviews": {"review": ["view"]},
    },
    "Content Manager": {
        "catalog": {
            "category": CRUD,
            "brand": CRUD,
            "product": CRUD,
            "productimage": CRUD,
            "productvariant": CRUD,
            "attribute": CRUD,
            "attributevalue": CRUD,
        },
        "reviews": {"review": CRUD, "reviewimage": CRUD},
        "notifications": {"newslettersubscriber": CRUD},
    },
    "Support Agent": {
        "accounts": {"user": ["view"], "address": CRUD},
        "orders": {"order": ["view", "change"], "orderitem": ["view"],
                   "orderstatushistory": ["view", "add"]},
        "payments": {"payment": ["view"]},
        "reviews": {"review": ["view", "change"]},
        "cart": {"cart": ["view"], "cartitem": ["view"],
                 "wishlistitem": ["view"]},
        "notifications": {"notification": ["view"]},
    },
}


def create_groups(app_config, **kwargs):
    """Create (idempotently) staff groups and grant them permissions.

    Runs for every ``post_migrate`` emission and always considers **all**
    models, so the result does not depend on signal ordering.
    """
    from django.apps import apps as global_apps
    from django.contrib.auth.management import create_permissions
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType

    verbosity = kwargs.get("verbosity", 0)
    using = kwargs.get("using", "default")

    registry = {
        f"{m._meta.app_label}.{m._meta.model_name}": m
        for m in global_apps.get_models()
    }

    # Make sure permissions exist for every model we are about to use.
    touched_apps = set()
    for spec in GROUP_PERMISSIONS.values():
        if spec == "*":
            touched_apps = {m._meta.app_label for m in registry.values()}
        else:
            touched_apps.update(spec.keys())
    for app_label in sorted(touched_apps):
        try:
            app_config_obj = global_apps.get_app_config(app_label)
        except LookupError:  # pragma: no cover
            continue
        create_permissions(
            app_config_obj, verbosity=0, interactive=False, using=using
        )

    for group_name, spec in GROUP_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        if spec == "*":
            group.permissions.set(Permission.objects.all())
            continue

        permissions = []
        for app_label, models_spec in spec.items():
            for model_name, actions in models_spec.items():
                model = registry.get(f"{app_label}.{model_name}")
                if model is None:
                    continue
                ct = ContentType.objects.get_for_model(model)
                for perm in Permission.objects.filter(content_type=ct):
                    if perm.codename.split("_", 1)[0] in actions:
                        permissions.append(perm)
        group.permissions.set(permissions)


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "User accounts, authentication and addresses"

    def ready(self):  # pragma: no cover - exercised via migrations/tests
        from django.db.models.signals import post_migrate

        # No sender: runs after every migrated app. Handler is idempotent and
        # always derives permissions from the full model registry.
        post_migrate.connect(create_groups)

        # Bind every login to a single active session/device.
        from . import signals  # noqa: F401  (registers user_logged_in)
