"""Forms for banner management."""
import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.banners.models import Banner


class BannerForm(forms.ModelForm):
    """Form for creating/editing banners with image preview."""

    class Meta:
        model = Banner
        fields = [
            "title", "slug", "image", "mobile_image",
            "click_action", "link_url", "modal_content",
            "button_text", "button_style",
            "valid_from", "valid_until", "is_active",
            "device_target", "countries", "user_segments", "min_order_count", "show_once_per_session",
            "is_popup",
            "position", "overlay_gradient", "text_alignment", "custom_css",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Summer Sale 2024"}),
            "slug": forms.TextInput(attrs={"placeholder": "summer-sale-2024"}),
            "valid_from": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
            "valid_until": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}
            ),
            "countries": forms.TextInput(
                attrs={"placeholder": "US, CA, GB", "class": "form-control"}
            ),
            "user_segments": forms.Textarea(attrs={"rows": 3, "class": "form-control mg-mono"}),
            "modal_content": forms.Textarea(attrs={"rows": 8, "placeholder": "<h2>Special Offer!</h2><p>Get 20% off all items...</p>"}),
            "custom_css": forms.Textarea(attrs={"rows": 3, "placeholder": ".banner-title { font-size: 3rem; }", "class": "form-control mg-mono"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_popup": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "show_once_per_session": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "overlay_gradient": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    # datetime-local inputs submit "2026-10-01T07:12"; keep legacy formats too.
    DATETIME_INPUT_FORMATS = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # countries: friendly comma-separated input (plain CharField — the
        # model JSONField's formfield would reject "US, CA" as invalid JSON
        # before clean_countries can parse it).
        self.fields["countries"] = forms.CharField(
            required=False,
            widget=forms.TextInput(attrs={"placeholder": "US, CA, GB", "class": "form-control"}),
            help_text=_("Comma-separated ISO country codes (e.g. US, CA, GB). Leave empty for all countries."),
            label=_("Countries"),
        )
        # Friendly help text
        self.fields["user_segments"].help_text = _("Choose who sees this banner.")
        self.fields["user_segments"].label = _("Audience")
        # Render the countries list as "US, CA" instead of Python repr "['US', 'CA']"
        countries_initial = self.initial.get("countries")
        if isinstance(countries_initial, list):
            self.initial["countries"] = ", ".join(countries_initial)
        for name in ("valid_from", "valid_until"):
            self.fields[name].input_formats = list(self.DATETIME_INPUT_FORMATS)
        # Bootstrap classes for every rendered widget
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.FileInput):
                widget.attrs.setdefault("class", "form-control")
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", "form-select")
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", "form-control")
            else:
                widget.attrs.setdefault("class", "form-control")

    def clean_countries(self):
        value = self.cleaned_data.get("countries")
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("["):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    raise ValidationError(_("Countries must be a valid JSON array."))
            else:
                value = [c.strip() for c in value.split(",") if c.strip()]
        if not isinstance(value, list):
            raise ValidationError(_("Countries must be a list."))
        codes = []
        for code in value:
            if not isinstance(code, str) or len(code) != 2:
                raise ValidationError(
                    _("Invalid country code: %(code)s. Use 2-letter ISO codes.")
                    % {"code": code}
                )
            codes.append(code.upper())
        return codes

    def clean_user_segments(self):
        value = self.cleaned_data.get("user_segments")
        if value in (None, ""):
            return {}
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise ValidationError(_("User segments must be a valid JSON object."))
        if not isinstance(value, dict):
            raise ValidationError(_("User segments must be an object."))
        allowed_keys = {"new_visitors", "returning", "has_orders"}
        for key in value:
            if key not in allowed_keys:
                raise ValidationError(
                    _("Invalid segment key: %(key)s. Allowed: %(allowed)s.")
                    % {"key": key, "allowed": allowed_keys}
                )
            if not isinstance(value[key], bool):
                raise ValidationError(
                    _("Segment '%(key)s' must be a boolean.") % {"key": key}
                )
        return value

    def clean(self):
        cleaned = super().clean()
        click_action = cleaned.get("click_action")
        link_url = cleaned.get("link_url")
        modal_content = cleaned.get("modal_content")

        if click_action == Banner.ClickAction.LINK and not link_url:
            self.add_error("link_url", _("Link URL is required when click action is 'Navigate to URL'."))
        if click_action == Banner.ClickAction.MODAL and not modal_content:
            self.add_error("modal_content", _("Modal content is required when click action is 'Open full-screen modal'."))
        return cleaned