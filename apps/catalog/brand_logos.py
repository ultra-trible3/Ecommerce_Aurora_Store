"""Configurable logo list for the reusable ``LogoMarquee`` component.

This is the single place to add, remove or replace marquee logos. The
``image`` value is a path relative to the static root, so it is resolved with
``{% static %}`` at render time.

The bundled assets in ``static/images/brands/`` are clearly-labelled
*placeholder* wordmarks (not real companies). Drop your real brand SVGs/PNGs
into ``static/images/brands/`` and point to them here.

To use a different list on a single page, pass it straight to the include::

    {% include "includes/logo_marquee.html" with logos=my_custom_list %}

Staff can also edit the list from the management portal
(``/management/settings/``). That value is stored in the ``Setting`` model
under the ``marquee_logos`` key as one ``Name | image`` pair per line; when it
is empty the ``BRAND_LOGOS`` list below is used as the fallback.
"""

BRAND_LOGOS = [
    {"name": "Acme", "image": "images/brands/acme.svg"},
    {"name": "Nimbus", "image": "images/brands/nimbus.svg"},
    {"name": "Vertex", "image": "images/brands/vertex.svg"},
    {"name": "Lumen", "image": "images/brands/lumen.svg"},
    {"name": "Orbit", "image": "images/brands/orbit.svg"},
    {"name": "Halo", "image": "images/brands/halo.svg"},
    {"name": "Cadence", "image": "images/brands/cadence.svg"},
    {"name": "Pinnacle", "image": "images/brands/pinnacle.svg"},
    {"name": "Zephyr", "image": "images/brands/zephyr.svg"},
    {"name": "Northwind", "image": "images/brands/northwind.svg"},
]

# Key used in the ``Setting`` key/value store for the dashboard-editable list.
MARQUEE_SETTING_KEY = "marquee_logos"


def parse_brand_logos(text):
    """Parse the dashboard textarea value into a logo list.

    Each non-empty line is ``Name | image`` (a comma also works as the
    separator). The image is a path relative to the static root, e.g.
    ``images/brands/acme.svg``. Lines without an image are ignored.
    """
    logos = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        separator = "|" if "|" in line else ("," if "," in line else None)
        if separator:
            name, image = line.split(separator, 1)
        else:
            name, image = "", line
        name = name.strip()
        image = image.strip()
        if not image:
            continue
        logos.append({"name": name or image.rsplit("/", 1)[-1], "image": image})
    return logos


def serialize_brand_logos(logos):
    """Render a logo list as the dashboard textarea value (inverse of parse)."""
    return "\n".join(f"{logo['name']} | {logo['image']}" for logo in logos)


def get_brand_logos():
    """Return the dashboard-configured logos, falling back to ``BRAND_LOGOS``."""
    # Imported lazily to avoid a catalog <-> notifications import cycle.
    from apps.notifications.models import Setting

    logos = parse_brand_logos(Setting.get(MARQUEE_SETTING_KEY, ""))
    return logos or list(BRAND_LOGOS)
