"""Account forms."""
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)
from django.utils.translation import gettext_lazy as _

from apps.core.forms import StyledFieldsMixin
from apps.core.validators import validate_image_file, validate_phone
from .models import Address

User = get_user_model()


class RegisterForm(StyledFieldsMixin, UserCreationForm):
    """Registration with email as the primary identifier."""

    first_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            "placeholder": "Jane", "autocomplete": "given-name",
        }),
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            "placeholder": "Doe", "autocomplete": "family-name",
        }),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            "placeholder": "you@example.com", "autocomplete": "email",
        }),
    )
    phone = forms.CharField(
        max_length=30,
        required=False,
        validators=[validate_phone],
        widget=forms.TextInput(attrs={
            "placeholder": "+1 (555) 000-0000", "autocomplete": "tel",
        }),
    )
    accept_terms = forms.BooleanField(
        required=True,
        label=_("I agree to the Terms of Service and Privacy Policy"),
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update({
            "placeholder": _("At least 8 characters"), "autocomplete": "new-password",
        })
        self.fields["password2"].widget.attrs.update({
            "placeholder": _("Repeat password"), "autocomplete": "new-password",
        })

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                _("An account with this email already exists. Try signing in.")
            )
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].strip().lower()
        user.phone = self.cleaned_data.get("phone", "")
        if commit:
            user.save()
        return user


class LoginForm(StyledFieldsMixin, AuthenticationForm):
    """Login form with remember-me support."""

    username = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={
            "placeholder": "you@example.com",
            "autocomplete": "email",
            "autofocus": True,
        }),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(attrs={
            "placeholder": _("Your password"),
            "autocomplete": "current-password",
        }),
    )
    remember = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Keep me signed in for 2 weeks"),
    )

    error_messages = {
        "invalid_login": _(
            "Please enter a correct email and password. "
            "Note that both fields may be case-sensitive."
        ),
        "inactive": _("This account is inactive. Please contact support."),
    }


class ProfileForm(StyledFieldsMixin, forms.ModelForm):
    """Editable customer profile fields."""

    class Meta:
        model = User
        fields = (
            "first_name", "last_name", "email", "phone",
            "profile_image", "date_of_birth",
        )
        widgets = {
            "first_name": forms.TextInput(attrs={
                "placeholder": "Jane", "autocomplete": "given-name",
            }),
            "last_name": forms.TextInput(attrs={
                "placeholder": "Doe", "autocomplete": "family-name",
            }),
            "email": forms.EmailInput(attrs={
                "placeholder": "you@example.com", "autocomplete": "email",
            }),
            "phone": forms.TextInput(attrs={
                "placeholder": "+1 (555) 000-0000", "autocomplete": "tel",
            }),
            "date_of_birth": forms.DateInput(
                attrs={"type": "date", "autocomplete": "bday"},
                format="%Y-%m-%d"
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user
        self.fields["profile_image"].validators.append(validate_image_file)
        self.fields["profile_image"].widget.attrs.update({
            "accept": "image/*",
            "data-crop": "1",
            "data-crop-ratio": "1",
            "data-crop-size": "512",
        })
        self.fields["email"].required = True
        self.fields["email"].help_text = _(
            "Used to sign in and to send order and delivery updates."
        )
        self.fields["phone"].help_text = _(
            "Optional — we only use it for delivery issues."
        )
        self.fields["date_of_birth"].help_text = _(
            "Optional — used for birthday offers."
        )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        qs = User.objects.filter(email__iexact=email)
        if self._user:
            qs = qs.exclude(pk=self._user.pk)
        if qs.exists():
            raise forms.ValidationError(_("This email is already in use."))
        return email


class AddressForm(forms.ModelForm):
    """Shipping/billing address form."""

    class Meta:
        model = Address
        fields = (
            "full_name", "phone", "address_line1", "address_line2",
            "city", "state", "country", "postal_code", "address_type",
            "is_default",
        )
        widgets = {
            "full_name": forms.TextInput(attrs={"placeholder": _("Full name")}),
            "phone": forms.TextInput(attrs={"placeholder": "+1 (555) 000-0000"}),
            "address_line1": forms.TextInput(
                attrs={"placeholder": _("Street address")}
            ),
            "address_line2": forms.TextInput(
                attrs={"placeholder": _("Apartment, suite, etc. (optional)")}
            ),
            "city": forms.TextInput(attrs={"placeholder": _("City")}),
            "state": forms.TextInput(attrs={"placeholder": _("State / Province")}),
            "country": forms.TextInput(attrs={"placeholder": _("Country")}),
            "postal_code": forms.TextInput(attrs={"placeholder": _("Postal code")}),
            "address_type": forms.Select(),
            "is_default": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user
        for name in ("full_name", "phone", "address_line1", "city", "postal_code"):
            self.fields[name].required = True
        if user and not self.instance.pk:
            self.fields["full_name"].initial = user.get_full_name()
            self.fields["phone"].initial = user.phone


class CustomPasswordChangeForm(StyledFieldsMixin, PasswordChangeForm):
    pass


class CustomPasswordResetForm(StyledFieldsMixin, PasswordResetForm):
    pass


class CustomSetPasswordForm(StyledFieldsMixin, SetPasswordForm):
    pass
