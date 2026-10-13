"""Forms used across the management portal."""
import re

from django import forms
from django.contrib.auth import get_user_model
from django.forms import formset_factory
from django.utils.translation import gettext_lazy as _

from apps.catalog.models import Brand, Category, Product
from apps.coupons.models import Coupon
from apps.orders.models import Order

User = get_user_model()


def _localize(field, label, lang):
    """Label an EN/AR input and mark its language for browsers/assistive tech."""
    field.label = label
    field.widget.attrs.setdefault("dir", "rtl" if lang == "ar" else "ltr")
    field.widget.attrs.setdefault("lang", lang)


class MultipleFileInput(forms.ClearableFileInput):
    """<input type="file" multiple> (Django 5 requires opting in)."""

    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """Validate every file produced by MultipleFileInput (see Django docs)."""

    def clean(self, data, initial=None):
        if isinstance(data, (list, tuple)):
            for item in data:
                super().clean(item, initial)
            return data
        return super().clean(data, initial)


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = (
            "name_en", "name_ar", "slug", "sku", "category", "brand",
            "price", "sale_price", "cost_price",
            "stock_quantity", "min_stock_level",
            "weight", "dimensions",
            "short_description_en", "short_description_ar",
            "full_description_en", "full_description_ar",
            "main_image",
            "status", "is_featured", "is_new_arrival", "is_best_seller",
        )
        widgets = {
            "name_en": forms.TextInput(attrs={
                "placeholder": _("Product name (English)"), "dir": "ltr",
            }),
            "name_ar": forms.TextInput(attrs={
                "placeholder": _("Product name (Arabic)"), "dir": "rtl", "lang": "ar",
            }),
            "sku": forms.TextInput(attrs={"placeholder": "SKU-001"}),
            "short_description_en": forms.Textarea(attrs={"rows": 2, "dir": "ltr"}),
            "short_description_ar": forms.Textarea(
                attrs={"rows": 2, "dir": "rtl", "lang": "ar"}
            ),
            "full_description_en": forms.Textarea(attrs={"rows": 6, "dir": "ltr"}),
            "full_description_ar": forms.Textarea(
                attrs={"rows": 6, "dir": "rtl", "lang": "ar"}
            ),
            "status": forms.Select(),
        }

    gallery_images = MultipleFileField(
        label=_("Gallery images"),
        required=False,
        help_text=_(
            "Extra photos for the product album — hold Ctrl/Cmd to select several."
        ),
        widget=MultipleFileInput(),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.filter(
            is_active=True
        ).order_by("position", "name")
        self.fields["category"].empty_label = _("Choose a category")
        self.fields["brand"].queryset = Brand.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["brand"].required = False
        # Generated from the English name on save.
        self.fields["slug"].required = False

        translations = {
            "name_en": (_("Product name (English)"), "en"),
            "name_ar": (_("Product name (Arabic)"), "ar"),
            "short_description_en": (_("Short description (English)"), "en"),
            "short_description_ar": (_("Short description (Arabic)"), "ar"),
            "full_description_en": (_("Full description (English)"), "en"),
            "full_description_ar": (_("Full description (Arabic)"), "ar"),
        }
        for field_name, (label, lang) in translations.items():
            if field_name in self.fields:
                _localize(self.fields[field_name], label, lang)
        # The English name drives slugs, emails and invoices: make it mandatory.
        self.fields["name_en"].required = True

        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price is not None and price < 0:
            raise forms.ValidationError(_("Price cannot be negative."))
        return price

    def clean(self):
        cleaned = super().clean()
        sale = cleaned.get("sale_price")
        price = cleaned.get("price")
        if sale is not None and price is not None and sale >= price:
            self.add_error(
                "sale_price", _("Sale price must be lower than the regular price.")
            )
        return cleaned


_HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


class ColorForm(forms.Form):
    """One colour option entered on the product form.

    Saved as a :class:`~apps.catalog.models.ProductVariant` linked to a
    ``Color`` :class:`~apps.catalog.models.AttributeValue`.
    """

    variant_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    name = forms.CharField(max_length=100, required=False, label=_("Colour name"))
    color_hex = forms.CharField(
        max_length=7,
        required=False,
        label=_("Swatch"),
        widget=forms.TextInput(attrs={"type": "color"}),
    )
    stock_quantity = forms.IntegerField(
        min_value=0, required=False, initial=0, label=_("Stock")
    )
    price = forms.DecimalField(
        max_digits=10, decimal_places=2, required=False, label=_("Price")
    )
    sku = forms.CharField(max_length=64, required=False, label=_("SKU"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.HiddenInput):
                continue
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        data = super().clean()
        if data.get("DELETE"):
            return data
        name = (data.get("name") or "").strip()
        color_hex = (data.get("color_hex") or "").strip()
        if name and color_hex and not _HEX_RE.match(color_hex):
            self.add_error(
                "color_hex", _("Enter a hex colour such as #ef4444.")
            )
        return data


# ``extra=3`` gives three blank rows when adding a product; the edit view
# trims that down once the existing colours are shown.
ColorFormSet = formset_factory(ColorForm, extra=3, can_delete=True)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = (
            "name_en", "name_ar", "slug", "parent",
            "description_en", "description_ar", "image",
            "is_active", "is_featured", "position",
        )
        widgets = {
            "description_en": forms.Textarea(attrs={"rows": 3, "dir": "ltr"}),
            "description_ar": forms.Textarea(
                attrs={"rows": 3, "dir": "rtl", "lang": "ar"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = Category.objects.filter(
            is_active=True
        ).order_by("position", "name")
        self.fields["parent"].required = False
        self.fields["parent"].empty_label = _("No parent (top level)")
        self.fields["slug"].required = False
        translations = {
            "name_en": (_("Name (English)"), "en"),
            "name_ar": (_("Name (Arabic)"), "ar"),
            "description_en": (_("Description (English)"), "en"),
            "description_ar": (_("Description (Arabic)"), "ar"),
        }
        for field_name, (label, lang) in translations.items():
            if field_name in self.fields:
                _localize(self.fields[field_name], label, lang)
        self.fields["name_en"].required = True
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = (
            "name_en", "name_ar", "slug", "logo",
            "description_en", "description_ar", "is_active",
        )
        widgets = {
            "description_en": forms.Textarea(attrs={"rows": 3, "dir": "ltr"}),
            "description_ar": forms.Textarea(
                attrs={"rows": 3, "dir": "rtl", "lang": "ar"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["slug"].required = False
        translations = {
            "name_en": (_("Name (English)"), "en"),
            "name_ar": (_("Name (Arabic)"), "ar"),
            "description_en": (_("Description (English)"), "en"),
            "description_ar": (_("Description (Arabic)"), "ar"),
        }
        for field_name, (label, lang) in translations.items():
            if field_name in self.fields:
                _localize(self.fields[field_name], label, lang)
        self.fields["name_en"].required = True
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = (
            "code", "description", "type", "value", "scope",
            "min_order_amount", "max_discount",
            "valid_from", "valid_until", "usage_limit", "per_user_limit",
            "applies_to_first_order_only", "is_active",
        )
        widgets = {
            "valid_from": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "valid_until": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("valid_from", "valid_until"):
            if name in self.initial and self.initial[name]:
                self.initial[name] = self.initial[name].strftime(
                    "%Y-%m-%dT%H:%M"
                )
        self.fields["valid_until"].required = False
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean_value(self):
        value = self.cleaned_data["value"]
        if value is None or value < 0:
            raise forms.ValidationError(_("Value cannot be negative."))
        return value


class StockAdjustForm(forms.Form):
    """Signed quantity adjustment for a product (or one of its variants)."""

    TRANSACTION_CHOICES = [
        ("adjustment", _("Manual adjustment")),
        ("purchase", _("Supplier purchase / restock")),
        ("return", _("Customer return")),
        ("restock", _("Restock")),
    ]
    product = forms.ModelChoiceField(queryset=Product.objects.all())
    variant_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    quantity = forms.IntegerField(
        help_text=_("Positive adds stock, negative removes stock.")
    )
    transaction_type = forms.ChoiceField(choices=TRANSACTION_CHOICES)
    note = forms.CharField(
        max_length=255, required=False,
        widget=forms.TextInput(attrs={"placeholder": _("Why is stock changing?")}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["product"].queryset = Product.objects.order_by("name")
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity == 0:
            raise forms.ValidationError(_("Quantity cannot be zero."))
        return quantity


class ReviewReplyForm(forms.Form):
    admin_reply = forms.CharField(
        label=_("Public reply"),
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control",
                                     "placeholder": _("Reply shown under the review…")}),
        required=False,
    )


class OrderEditForm(forms.ModelForm):
    """Staff-facing edits to customer contact, shipping address and notes."""

    class Meta:
        model = Order
        fields = (
            "email", "guest_name", "guest_phone",
            "shipping_full_name", "shipping_phone",
            "shipping_address_line1", "shipping_address_line2",
            "shipping_city", "shipping_state", "shipping_country",
            "shipping_postal_code",
            "notes", "internal_notes",
        )
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
            "internal_notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class CustomerEditForm(forms.ModelForm):
    """Staff-facing edits to a customer's profile and access."""

    class Meta:
        model = User
        fields = (
            "first_name", "last_name", "email", "username",
            "phone", "email_verified", "is_active",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")

    def clean_email(self):
        email = self.cleaned_data["email"]
        qs = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(_("A user with this email already exists."))
        return email
