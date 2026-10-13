"""Template tags for the core app."""
import json
import os

from django import template
from django.conf import settings
from django.templatetags.static import static as static_url
from django.urls import reverse
from django.utils.translation import get_language, get_language_info

register = template.Library()


@register.simple_tag
def static_v(path):
    """Like ``{% static %}`` but appends ``?v=<mtime>`` so browsers never
    serve a stale copy of a file that changed after it was cached."""
    from django.contrib.staticfiles import finders

    resolved = finders.find(path) or ""
    try:
        version = int(os.path.getmtime(resolved))
    except (OSError, ValueError, TypeError):
        version = 0
    return f"{static_url(path)}?v={version}"


@register.filter
def currency(value):
    """Format a number as currency: ``{{ product.price|currency }}``."""
    from apps.core.utils import money

    return f"{settings.CURRENCY_SYMBOL}{money(value):,.2f}"


@register.filter
def subtract(value, arg):
    """Return ``value - arg``."""
    try:
        return value - arg
    except (TypeError, ValueError):
        return value


@register.filter
def percentage(part, whole):
    """Return an integer percentage of ``part`` out of ``whole``."""
    try:
        whole = float(whole)
        if whole <= 0:
            return 0
        return round(float(part) / whole * 100)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def get_item(mapping, key):
    """Dictionary lookup in templates: ``{{ d|get_item:key }}``."""
    if hasattr(mapping, "get"):
        return mapping.get(key)
    return None


@register.filter
def filesize(value):
    """Human readable file size."""
    try:
        size = float(value)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@register.filter
def json_script_safe(value):
    """Serialize a python object into a JSON string for data attributes."""
    return json.dumps(value)


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    """Merge current querystring params with new values."""
    request = context.get("request")
    if request is None:
        return ""
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value is None or value == "":
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"


@register.inclusion_tag("includes/pagination.html", takes_context=True)
def paginate(context, page_obj, **kwargs):
    """Render pagination controls."""
    return {
        "page_obj": page_obj,
        "request": context.get("request"),
        **kwargs,
    }


@register.simple_tag
def language_name(lang_code):
    """Return the native name of a language."""
    try:
        return get_language_info(lang_code)["name_local"]
    except KeyError:
        return lang_code


@register.simple_tag(takes_context=True)
def change_lang_url(context, lang_code):
    """Generate URL for switching language."""
    request = context.get("request")
    if request is None:
        return ""
    path = request.path
    return f"/{lang_code}{path}" if not path.startswith(f"/{lang_code}/") else path.replace(f"/{get_language()}/", f"/{lang_code}/", 1)


@register.inclusion_tag("includes/language_switcher.html", takes_context=True)
def language_switcher(context):
    """Render language switcher dropdown."""
    request = context.get("request")
    current_lang = get_language()
    return {
        "current_lang": current_lang,
        "languages": settings.LANGUAGES,
        "request": request,
    }


@register.simple_tag
def is_rtl(lang_code=None):
    """Check if a language is RTL."""
    from django.utils.translation import get_language
    from django.conf import settings
    
    if lang_code is None:
        lang_code = get_language()
    
    rtl_languages = [code for code, name in settings.LANGUAGES if code in ["ar", "he", "fa", "ur"]]
    return lang_code in rtl_languages
