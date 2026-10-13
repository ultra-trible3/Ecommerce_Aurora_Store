"""Shared form helpers."""
from django import forms


def _style_widget(field):
    """Give a field's widget the Bootstrap class it needs to render styled."""
    widget = field.widget
    if isinstance(
        widget,
        (forms.CheckboxInput, forms.RadioSelect, forms.CheckboxSelectMultiple),
    ):
        css = "form-check-input"
    elif isinstance(widget, forms.Select):
        css = "form-select"
    else:
        css = "form-control"
    attrs = widget.attrs
    classes = attrs.get("class", "").split()
    if css not in classes:
        classes.append(css)
    attrs["class"] = " ".join(classes)


class StyledFieldsMixin:
    """Add Bootstrap classes to every widget so templates can render bare {{ field }}."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            _style_widget(field)
