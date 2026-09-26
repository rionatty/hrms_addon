# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The sign-in page's look: the desk theme's colours, the branding's words
and picture, made safe to put in a stylesheet.

No Frappe import, like the other *_rules.py modules, so
scripts/verify_login_page.py exercises it without a bench. www/login.py
reads the settings and hands them here; www/login.html and www/login.css
draw the page.

The page is Frappe's own sign-in card, untouched (login.js drives it by
its classes and ids), set beside a brand panel in the desk theme's
colours, so the page and the desk behind it look like one product. The
colours come from HRMS Addon Theme Settings when it is switched on, else
the shipped theme; the tagline and the panel's picture from HRMS Addon
Branding.
"""

import re
from urllib.parse import quote

# the theme's colours the page uses: (theme field, CSS variable on the page)
COLOURS = (
    ("primary_navy", "--hal-primary"),
    ("section_header_colour", "--hal-primary-2"),
    ("accent_colour", "--hal-accent"),
    ("selected_highlight", "--hal-highlight"),
)

# shown under the product name when the branding sets none
DEFAULT_TAGLINE = "HR, leave, payroll and recruitment in one place."

_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")

# where the panel's picture may come from: the site's public files (a guest
# on the sign-in page cannot load a private one) or an https address
IMAGE_SOURCES = ("/files/", "https://")
# kept as they are in the picture's address; everything else is
# percent-encoded, so nothing in it can end the url('') it is put in, the
# style element around that, or start another rule
_URL_KEEP = "/:?=&%+,@!$*#~"
_LONE_PERCENT = re.compile(r"%(?![0-9a-fA-F]{2})")


def safe_colour(value, fallback):
    """A hex colour as the stylesheet may take it, else the fallback."""
    value = (value or "").strip()
    return value if _HEX.fullmatch(value) else fallback


def safe_image(url):
    """The panel's picture as the stylesheet may take it: a public file of
    the site's or an https address, with any space, quote, bracket and the
    like percent-encoded (file names often carry spaces). Else "" and the
    panel shows its colours alone."""
    url = (url or "").strip()
    if not any(url.startswith(source) and len(url) > len(source) for source in IMAGE_SOURCES):
        return ""
    return quote(_LONE_PERCENT.sub("%25", url), safe=_URL_KEEP)


def look(theme, defaults, tagline=None, image=None):
    """What the page needs: {"colours": [(variable, colour)], "tagline",
    "image"}.

    theme: the Theme Settings colours in force ({field: colour}, empty when
    it is switched off); defaults: the shipped theme's ({field: colour}).
    A colour that is not a plain hex one falls back to the shipped theme.
    """
    theme, defaults = theme or {}, defaults or {}
    return {
        "colours": [(variable, safe_colour(theme.get(field), defaults.get(field) or "#14395E"))
                    for field, variable in COLOURS],
        "tagline": (tagline or "").strip() or DEFAULT_TAGLINE,
        "image": safe_image(image),
    }
