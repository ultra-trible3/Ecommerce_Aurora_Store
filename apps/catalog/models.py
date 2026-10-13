"""Catalog: categories, brands, products, variants and attributes."""
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.core.models import SEOModel, SlugModel, TimeStampedModel
from apps.core.validators import validate_image_file


class Category(SEOModel, SlugModel, TimeStampedModel):
    """Hierarchical product category (self-referencing parent)."""

    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="categories/%Y/%m/", blank=True, validators=[validate_image_file]
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    position = models.PositiveIntegerField(default=0, db_index=True)

    class Meta(SlugModel.Meta):
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ("position", "name")
        indexes = [models.Index(fields=["is_active", "position"])]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("catalog:category", kwargs={"slug": self.slug})

    @property
    def full_name(self):
        """Category path such as ``Electronics > Phones``."""
        parts = [self.name]
        node = self.parent
        while node is not None:
            parts.append(node.name)
            node = node.parent
        return " › ".join(reversed(parts))

    def get_children(self):
        return self.children.filter(is_active=True).order_by("position", "name")

    @property
    def all_descendants(self):
        """Flattened queryset of every descendant category id."""
        ids = [self.pk]
        stack = [self]
        while stack:
            node = stack.pop()
            for child in node.children.all():
                ids.append(child.pk)
                stack.append(child)
        return Category.objects.filter(pk__in=ids)


class Brand(SEOModel, SlugModel, TimeStampedModel):
    """Product brand."""

    name = models.CharField(max_length=150, unique=True)
    logo = models.ImageField(
        upload_to="brands/%Y/%m/", blank=True, validators=[validate_image_file]
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta(SlugModel.Meta):
        verbose_name = _("brand")
        verbose_name_plural = _("brands")
        ordering = ("name",)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("catalog:brand", kwargs={"slug": self.slug})


def product_name_q(query):
    """Match a product by SKU or by its name in *either* language.

    ``name__icontains`` is rewritten by modeltranslation to the active
    language only, which would hide every hit from the other one.
    """
    from django.db.models import Q

    return (
        Q(name_en__icontains=query)
        | Q(name_ar__icontains=query)
        | Q(sku__icontains=query)
    )


def both_languages_q(field, query):
    """``<field>__icontains`` across the English and Arabic columns."""
    from django.db.models import Q

    return Q(**{f"{field}_en__icontains": query}) | Q(
        **{f"{field}_ar__icontains": query}
    )


class ProductQuerySet(models.QuerySet):
    """Custom queryset with useful catalog filters."""

    def active(self):
        return self.filter(status=Product.Status.ACTIVE)

    def featured(self):
        return self.active().filter(is_featured=True)

    def new_arrivals(self):
        return self.active().filter(is_new_arrival=True)

    def best_sellers(self):
        return self.active().filter(is_best_seller=True)

    def on_sale(self):
        return self.active().filter(sale_price__isnull=False).exclude(
            sale_price__lte=0
        )

    def in_stock(self):
        return self.filter(stock_quantity__gt=0)

    def search(self, query):
        if not query:
            return self
        from django.db.models import Q

        return self.filter(
            product_name_q(query)
            | both_languages_q("short_description", query)
            | both_languages_q("full_description", query)
            | both_languages_q("brand__name", query)
            | both_languages_q("category__name", query)
        ).distinct()


class Product(SEOModel, TimeStampedModel):
    """A sellable product."""

    class Status(models.TextChoices):
        ACTIVE = "active", _("Active")
        DRAFT = "draft", _("Draft")
        ARCHIVED = "archived", _("Archived")

    name = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, db_index=True)
    sku = models.CharField(max_length=64, unique=True, db_index=True)
    short_description = models.CharField(max_length=500, blank=True)
    full_description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products", db_index=True
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )

    price = models.DecimalField(max_digits=10, decimal_places=2)
    sale_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    stock_quantity = models.PositiveIntegerField(default=0, db_index=True)
    min_stock_level = models.PositiveIntegerField(default=5)
    reserved_quantity = models.PositiveIntegerField(default=0)

    weight = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True,
        help_text=_("Weight in kg."),
    )
    dimensions = models.CharField(
        max_length=100, blank=True, help_text=_('e.g. "10 × 20 × 5 cm"')
    )

    main_image = models.ImageField(
        upload_to="products/%Y/%m/", blank=True, validators=[validate_image_file]
    )

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    is_featured = models.BooleanField(default=False, db_index=True)
    is_new_arrival = models.BooleanField(default=False, db_index=True)
    is_best_seller = models.BooleanField(default=False, db_index=True)

    rating_average = models.DecimalField(
        max_digits=3, decimal_places=2, default=0
    )
    rating_count = models.PositiveIntegerField(default=0)
    sold_count = models.PositiveIntegerField(default=0, db_index=True)
    view_count = models.PositiveIntegerField(default=0)

    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["status", "is_featured"]),
            models.Index(fields=["status", "price"]),
            models.Index(fields=["status", "category", "brand"]),
            models.Index(fields=["status", "-sold_count"]),
            models.Index(fields=["status", "-rating_average"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(price__gte=0), name="product_price_non_negative"
            ),
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("catalog:detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        from apps.core.models import generate_slug, sync_default_language

        sync_default_language(self, "name")
        if not self.slug:
            # Always slugify the English name: URLs must stay identical in
            # both languages (slugs are not translated).
            source = getattr(self, "name_en", None) or self.name
            self.slug = generate_slug(self, source, queryset=Product.objects)
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Pricing / availability helpers (always read from DB)
    # ------------------------------------------------------------------
    @property
    def is_on_sale(self):
        return self.sale_price is not None and self.sale_price < self.price

    @property
    def current_price(self):
        return self.sale_price if self.is_on_sale else self.price

    @property
    def discount_percent(self):
        if not self.is_on_sale:
            return 0
        return round((1 - float(self.sale_price) / float(self.price)) * 100)

    @property
    def available_quantity(self):
        """Stock available to sell (base stock minus reservations)."""
        if self.has_variants:
            return sum(v.available_quantity for v in self.variants.all())
        return max(int(self.stock_quantity) - int(self.reserved_quantity), 0)

    @property
    def has_variants(self):
        return self.variants.exists()

    @property
    def is_in_stock(self):
        return self.available_quantity > 0

    @property
    def stock_status(self):
        if self.is_in_stock:
            if self.stock_quantity <= self.min_stock_level and not self.has_variants:
                return "low"
            return "in"
        return "out"

    @property
    def normal_price(self):
        return self.price

    @property
    def review_count(self):
        return self.rating_count

    @property
    def category_path(self):
        return self.category.full_name

    @property
    def json_ld(self):
        """Schema.org structured data for this product."""
        data = {
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": self.name,
            "sku": self.sku,
            "description": (self.short_description or self.full_description)[:500],
            "brand": {"@type": "Brand", "name": self.brand.name}
            if self.brand else None,
            "offers": {
                "@type": "Offer",
                "price": str(self.current_price),
                "priceCurrency": "USD",
                "availability": "https://schema.org/InStock"
                if self.is_in_stock
                else "https://schema.org/OutOfStock",
                "url": self.get_absolute_url(),
            },
        }
        if self.rating_count:
            data["aggregateRating"] = {
                "@type": "AggregateRating",
                "ratingValue": str(self.rating_average),
                "reviewCount": self.rating_count,
            }
        if not data.get("brand"):
            data.pop("brand", None)
        return data


class ProductImage(models.Model):
    """Extra gallery image for a product."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(
        upload_to="products/gallery/%Y/%m/", validators=[validate_image_file]
    )
    alt = models.CharField(max_length=200, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")

    def __str__(self):
        return _("Image for %(product)s") % {"product": self.product}

    @property
    def alt_text(self):
        return self.alt or self.product.name


class Attribute(models.Model):
    """A variant-defining attribute such as Color or Size."""

    name = models.CharField(max_length=100, unique=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "name")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from apps.core.models import sync_default_language

        sync_default_language(self, "name")
        super().save(*args, **kwargs)


class AttributeValue(models.Model):
    """A single value of an attribute (e.g. ``Red``, ``XL``)."""

    attribute = models.ForeignKey(
        Attribute, on_delete=models.CASCADE, related_name="values"
    )
    value = models.CharField(max_length=100)
    color_hex = models.CharField(
        max_length=7, blank=True, help_text=_('Optional hex color e.g. "#ef4444"')
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "value")
        unique_together = ("attribute", "value")

    def __str__(self):
        return f"{self.attribute}: {self.value}"

    def save(self, *args, **kwargs):
        from apps.core.models import sync_default_language

        sync_default_language(self, "value")
        super().save(*args, **kwargs)


class ProductVariant(models.Model):
    """A specific sellable combination (size/color) of a product."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variants"
    )
    name = models.CharField(max_length=150, help_text=_('e.g. "Red / XL"'))
    sku = models.CharField(max_length=64, unique=True)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text=_("Leave blank to use the product price."),
    )
    sale_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    stock_quantity = models.PositiveIntegerField(default=0)
    reserved_quantity = models.PositiveIntegerField(default=0)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    attributes = models.ManyToManyField(
        AttributeValue, related_name="variants", blank=True
    )

    class Meta:
        ordering = ("position", "id")
        indexes = [models.Index(fields=["product", "is_active"])]

    def __str__(self):
        return f"{self.product.name} – {self.name}"

    @property
    def available_quantity(self):
        return max(int(self.stock_quantity) - int(self.reserved_quantity), 0)

    @property
    def is_in_stock(self):
        return self.available_quantity > 0

    @property
    def current_price(self):
        if self.sale_price is not None and (
            self.price is None or self.sale_price < self.price
        ):
            return self.sale_price
        return self.price if self.price is not None else self.product.current_price

    @property
    def base_price(self):
        return self.price if self.price is not None else self.product.price

    @property
    def is_on_sale(self):
        return self.sale_price is not None and self.price is not None and (
            self.sale_price < self.price
        )

    @property
    def discount_percent(self):
        if not self.is_on_sale:
            return 0
        return round((1 - float(self.sale_price) / float(self.price)) * 100)

    @property
    def color_value(self):
        """The variant's *Color* ``AttributeValue`` (or ``None``)."""
        for value in self.attributes.all():
            attribute = value.attribute
            names = {
                (attribute.name_en or "").strip().lower(),
                (attribute.name_ar or "").strip().lower(),
                (attribute.name or "").strip().lower(),
            }
            if names & {"color", "colour", "اللون"}:
                return value
        return None

    @property
    def color_hex(self):
        """Hex swatch for this variant's colour, empty when not a colour."""
        value = self.color_value
        return value.color_hex if value else ""


class StockAlert(TimeStampedModel):
    """Email subscription for back-in-stock notifications."""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="stock_alerts"
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="stock_alerts",
    )
    email = models.EmailField()
    is_active = models.BooleanField(default=True)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = (("product", "variant", "email"),)
        ordering = ("-created_at",)

    def __str__(self):
        target = self.variant.name if self.variant else self.product.name
        return f"{self.email} — {target}"

    def notify_and_deactivate(self):
        self.is_active = False
        self.notified_at = timezone.now()
        self.save(update_fields=["is_active", "notified_at"])
