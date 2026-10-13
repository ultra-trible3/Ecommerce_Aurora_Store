"""Checkout form — every field validated server-side."""
from django import forms
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

from apps.core.forms import StyledFieldsMixin
from apps.core.validators import validate_phone
from apps.orders.models import ShippingMethod

PAYMENT_CHOICES = (
    ("cod", _("Cash on delivery")),
    ("stripe", _("Credit / debit card (Stripe)")),
    ("paypal", _("PayPal")),
)


def _payment_choices():
    """Only offer gateways that are actually configured."""
    from django.conf import settings

    choices = [("cod", _("Cash on delivery"))]
    if settings.STRIPE_SECRET_KEY:
        choices.append(("stripe", _("Credit / debit card (Stripe)")))
    if settings.PAYPAL_CLIENT_ID:
        choices.append(("paypal", _("PayPal")))
    return choices


class CheckoutForm(StyledFieldsMixin, forms.Form):
    """Single form covering customer info, addresses, shipping and payment."""

    # Step 2 — customer
    email = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={
            "placeholder": "you@example.com", "autocomplete": "email",
        }),
    )
    full_name = forms.CharField(
        max_length=150,
        label=_("Full name"),
        widget=forms.TextInput(attrs={
            "placeholder": _("Jane Doe"), "autocomplete": "name",
        }),
    )
    phone = forms.CharField(
        max_length=30,
        label=_("Phone"),
        validators=[validate_phone],
        widget=forms.TextInput(attrs={
            "placeholder": "+1 (555) 000-0000", "autocomplete": "tel",
        }),
    )

    # Step 3 — shipping address
    address_line1 = forms.CharField(
        max_length=255,
        label=_("Address line 1"),
        widget=forms.TextInput(attrs={
            "placeholder": _("128 Market Street"), "autocomplete": "address-line1",
        }),
    )
    address_line2 = forms.CharField(
        max_length=255, required=False, label=_("Address line 2"),
        widget=forms.TextInput(attrs={
            "placeholder": _("Apartment, suite (optional)"),
            "autocomplete": "address-line2",
        }),
    )
    city = forms.CharField(
        max_length=100, label=_("City"),
        widget=forms.TextInput(attrs={"autocomplete": "address-level2"}),
    )
    state = forms.CharField(
        max_length=100, required=False, label=_("State / Province"),
        widget=forms.TextInput(attrs={"autocomplete": "address-level1"}),
    )
    country = forms.CharField(
        max_length=100, initial=_("United States"), label=_("Country"),
        widget=forms.TextInput(attrs={"autocomplete": "country-name"}),
    )
    postal_code = forms.CharField(
        max_length=20, label=_("Postal code"),
        widget=forms.TextInput(attrs={"autocomplete": "postal-code"}),
    )

    # Step 4 — billing
    same_as_shipping = forms.BooleanField(required=False, initial=True)
    billing_full_name = forms.CharField(max_length=150, required=False)
    billing_phone = forms.CharField(max_length=30, required=False,
                                    validators=[validate_phone])
    billing_address_line1 = forms.CharField(max_length=255, required=False)
    billing_address_line2 = forms.CharField(max_length=255, required=False)
    billing_city = forms.CharField(max_length=100, required=False)
    billing_state = forms.CharField(max_length=100, required=False)
    billing_country = forms.CharField(max_length=100, required=False)
    billing_postal_code = forms.CharField(max_length=20, required=False)

    # Step 5 — shipping method
    shipping_method = forms.ChoiceField(
        choices=[], label=_("Shipping method"),
        widget=forms.RadioSelect,
    )

    # Step 6 — coupon
    coupon_code = forms.CharField(
        max_length=64, required=False, label=_("Coupon code")
    )

    # Step 7 — payment
    payment_method = forms.ChoiceField(
        choices=PAYMENT_CHOICES, initial="cod", label=_("Payment method"),
        widget=forms.RadioSelect,
    )

    notes = forms.CharField(
        max_length=1000, required=False, label=_("Order notes"),
        widget=forms.Textarea(attrs={
            "rows": 3,
            "placeholder": _("Delivery instructions, gate code, gift note…"),
        }),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        methods = ShippingMethod.objects.filter(is_active=True).order_by("position")
        self.fields["shipping_method"].choices = [
            (m.code, f"{m.name} — {m.estimated_days}") for m in methods
        ]
        if methods:
            self.fields["shipping_method"].initial = methods.first().code
        self.fields["payment_method"].choices = _payment_choices()
        if user and user.is_authenticated:
            self.fields["email"].initial = user.email
            self.fields["full_name"].initial = user.get_full_name()
            self.fields["phone"].initial = user.phone

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("same_as_shipping"):
            required_billing = (
                "billing_full_name", "billing_address_line1",
                "billing_city", "billing_postal_code",
            )
            for field in required_billing:
                if not cleaned.get(field):
                    self.add_error(
                        field, _("Required when billing address differs.")
                    )
            if cleaned.get("billing_full_name") and not cleaned.get(
                "billing_country"
            ):
                cleaned["billing_country"] = _("United States")
        else:
            # Mirror shipping details for a consistent snapshot.
            for src, dst in (
                ("full_name", "billing_full_name"),
                ("phone", "billing_phone"),
                ("address_line1", "billing_address_line1"),
                ("address_line2", "billing_address_line2"),
                ("city", "billing_city"),
                ("state", "billing_state"),
                ("country", "billing_country"),
                ("postal_code", "billing_postal_code"),
            ):
                cleaned[dst] = cleaned.get(src, "")
        return cleaned

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        validate_email(email)
        return email
