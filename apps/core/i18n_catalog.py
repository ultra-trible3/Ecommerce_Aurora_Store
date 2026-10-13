"""Client-side (JavaScript) message catalog.

Strings rendered by static JS scripts — toast titles, drawer titles, avatar
upload messages — are marked for translation *here* so ``makemessages``
extracts them into the ordinary ``django.po`` catalog alongside server-side
strings.  The :func:`apps.core.context_processors.js_catalog` context
processor then renders the translated map to the page as ``window.aul10n``
(see ``templates/base.html``), and JS code looks a message up with
``window.t(msg)`` / ``window.ts(msg, ...)``, falling back to the English
source when a translation is missing.

- Positional ``%s`` placeholders mark interpolated values (quantity counts,
  file names, dimensions); JS substitutes them via ``window.ts`` while the
  Arabic translation may reorder them freely.
- Keep every entry identical (character-for-character) to the string passed
  to ``t()``/``ts()`` in the JS source, otherwise the lookup falls back to
  the untranslated English text.
"""
from django.utils.translation import gettext_lazy as _

# fmt: off
JS_MESSAGES = [
    # Generic toast / fallback titles
    _("Close"),
    _("Notice"),
    _("Error"),
    _("Oops"),
    _("Notifications"),
    _("Compare"),
    _("Done"),
    _("Retry"),
    _("Shopping cart"),
    _("Saved for later"),

    # Wishlist
    _("Added to wishlist"),
    _("Removed from wishlist"),
    _("Saved for later."),
    _("Removed from your wishlist."),
    _("Could not update wishlist."),

    # Compare
    _("Added to compare"),
    _("Removed from compare"),
    _("Open the compare page to see them side by side."),
    _("Removed from your compare list."),
    _("Could not update compare list."),

    # Product pages / drawers / generic AJAX feedback
    _("In stock (%s available)"),
    _("Out of stock"),
    _("Could not load right now."),
    _("Request failed."),
    _("Updated."),
    _("Network error, please retry."),
    _("Could not subscribe right now."),
    _("Subscribed!"),
    _("Hmm..."),

    # Notifications
    _("Could not update notification."),
    _("All notifications marked as read."),
    _("New notification"),
    _(" (+%s more)"),

    # Checkout wizard
    _("Missing details"),
    _("Please complete the highlighted fields."),
    _("Processing..."),
    _("Place order — %s"),

    # Stripe payment page
    _("Pay %s"),
    _("Processing…"),
    _("Payment could not be verified."),
    _("Stripe is not configured on this deployment."),

    # Order returns
    _("Please select at least one item to return."),

    # Product detail page
    _("Link copied"),
    _("Product link copied to your clipboard."),
    _("Something went wrong. Please try again."),

    # Avatar upload / crop
    _("New photo preview"),
    _("Cropped photo ready — %s (%s×%s)"),
    _("That file is not an image — choose a JPG or PNG."),
    _("Image is too large (max 5 MB)."),
    _("Photo selected: %s"),
]
# fmt: on