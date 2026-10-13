"""Configurable content for the homepage Deals & Promotions mosaic.

This is the single place to edit the promotional tiles shown above the
"Recently viewed" section on the homepage. Each tile is a dict:

    key        unique slug (used for the CSS hook / ordering)
    eyebrow    small uppercase label, e.g. "Mega Deals"
    title      the headline offer
    subtitle   one-line supporting copy
    badge      short discount label, e.g. "-60%" / "BOGO" / "VIP"
    cta        call-to-action button text
    route      Django URL *name* the tile links to (resolved in the template)
    query      optional querystring appended to the link (may be "")
    icon       Bootstrap Icons class shown as the decorative artwork
    tone       colour scheme: wine | sand | steel | ink (see main.css)
    size       mosaic slot: hero | wide | sm
    image      optional static-relative path (e.g. "images/deals/x.jpg").
               Leave empty to use the gradient + icon artwork, so we never
               point at assets that do not exist.

The grid is designed for four tiles (one hero, one wide, two small). Adding
or removing a tile degrades gracefully: the grid reflows without overflow.
"""
from django.utils.translation import gettext_lazy as _

DEALS = [
    {
        "key": "mega",
        "eyebrow": _("Mega Deals"),
        "title": _("Up to 60% off"),
        "subtitle": _("Our biggest markdowns across every department."),
        "badge": "-60%",
        "cta": _("Shop mega deals"),
        "route": "catalog:shop",
        "query": "sale=1",
        "icon": "bi-fire",
        "tone": "wine",
        "size": "hero",
        "image": "",
    },
    {
        "key": "super",
        "eyebrow": _("Super Deals"),
        "title": _("Buy 1, get 1 free"),
        "subtitle": _("On selected bestsellers — while stock lasts."),
        "badge": "BOGO",
        "cta": _("Grab the offer"),
        "route": "catalog:shop",
        "query": "sort=discount",
        "icon": "bi-lightning-charge-fill",
        "tone": "sand",
        "size": "wide",
        "image": "",
    },
    {
        "key": "special",
        "eyebrow": _("Special Deals"),
        "title": _("Save 25% today"),
        "subtitle": _("Flash prices refreshed every day."),
        "badge": "-25%",
        "cta": _("Shop now"),
        "route": "catalog:shop",
        "query": "sale=1",
        "icon": "bi-percent",
        "tone": "steel",
        "size": "sm",
        "image": "",
    },
    {
        "key": "exclusive",
        "eyebrow": _("Exclusive Offers"),
        "title": _("Members save more"),
        "subtitle": _("Hand-picked rewards for our community."),
        "badge": "VIP",
        "cta": _("Unlock offers"),
        "route": "catalog:shop",
        "query": "featured=1",
        "icon": "bi-gem",
        "tone": "ink",
        "size": "sm",
        "image": "",
    },
]
