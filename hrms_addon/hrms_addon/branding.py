# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""White-label branding.

Frappe already owns every field this needs — they are just scattered
across two Singles and consumed by three different resolution chains.
This module is one screen ("HRMS Addon Branding") that writes them all,
so a deployment is branded from one place instead of five.

Where each value actually lands (verified against frappe v16.33):

  product_name  -> Website Settings.app_name
                   * desk browser tab: www/desk.html <title>{{ app_name }}</title>
                     resolved as Website Settings.app_name
                       or System Settings.app_name or "Frappe"
                   * login page heading and "Login To {0}" emails (www/login.py)

  company_logo  -> Website Settings.app_logo  AND  Navbar Settings.app_logo
                   Two writes, deliberately. The chains differ:
                     desk navbar  : get_app_logo() = Website Settings.app_logo
                                    -> Navbar Settings.app_logo -> app_logo_url hook
                     /app/desktop : desktop.py reads Navbar Settings.app_logo ONLY
                                    (it never looks at Website Settings)
                     login page   : get_app_logo(), same as the desk navbar
                   Writing both keeps every surface in step.

  favicon       -> Website Settings.favicon
                   www/desk.html and templates/base.html both fall back to
                   frappe-favicon.svg when this is empty.

  splash_image  -> Website Settings.splash_image
                   templates/includes/splash_screen.html — the logo shown
                   while the desk boots.

  footer_powered-> Website Settings.footer_powered
                   templates/includes/footer/footer_info.html does
                     {% if footer_powered %}{{ footer_powered }}
                     {% else %}{% include ".../footer_powered.html" %}{% endif %}
                   ERPNext ships its own footer_powered.html ("Powered by
                   ERPNext") that shadows Frappe's ("Built on Frappe").
                   Setting this field beats both — no template override.

The launcher tile for this app is NOT set from here: tiles read the
per-app `add_to_apps_screen` / `app_logo_url` hooks, which are static.
See hooks.py.

SAFETY RULE: a blank field here never clears the corresponding upstream
value. Migrate runs this on every deploy, and silently wiping a logo
somebody set by hand in Website Settings would be a nasty surprise. Only
non-empty values are pushed.
"""

import frappe

# our fieldname -> (target doctype, target fieldname)
BRANDING_TARGETS = {
    "product_name":   [("Website Settings", "app_name")],
    "company_logo":   [("Website Settings", "app_logo"), ("Navbar Settings", "app_logo")],
    "favicon":        [("Website Settings", "favicon")],
    "splash_image":   [("Website Settings", "splash_image")],
    "footer_powered": [("Website Settings", "footer_powered")],
}

# Shipped placeholder. Replace the file itself rather than this path —
# hooks.py points at it too.
PLACEHOLDER_LOGO = "/assets/hrms_addon/images/company-logo-placeholder.svg"


def get_settings():
    """The Branding Single, or None on a site where it does not exist yet.

    Runs during boot and during migrate, so it must never raise.
    """
    try:
        if not frappe.db.exists("DocType", "HRMS Addon Branding"):
            return None
        return frappe.get_cached_doc("HRMS Addon Branding")
    except Exception:
        return None


def apply_branding(force=False):
    """Push the branding values into Website Settings / Navbar Settings.

    Idempotent: only fields that are set here AND differ from what is
    already stored get written, so repeat migrates are no-ops and a
    hand-edited value is left alone when our field is blank.

    Returns the list of "Doctype.field" that actually changed — the
    Branding form shows it, so it is obvious what a click did.
    """
    settings = get_settings()
    if not settings or not (settings.get("enabled") or force):
        return []

    changed = []
    touched_doctypes = set()

    for fieldname, targets in BRANDING_TARGETS.items():
        value = (settings.get(fieldname) or "").strip()
        if not value:
            continue  # SAFETY RULE — never clear upstream from a blank field
        for target_dt, target_field in targets:
            try:
                current = frappe.db.get_single_value(target_dt, target_field)
            except Exception:
                continue
            if (current or "") == value:
                continue
            frappe.db.set_single_value(target_dt, target_field, value)
            changed.append("%s.%s" % (target_dt, target_field))
            touched_doctypes.add(target_dt)

    for dt in touched_doctypes:
        frappe.clear_document_cache(dt, dt)
    if changed:
        # app_name/app_logo/favicon all ride the boot payload and the
        # website context, both of which are cached.
        frappe.clear_cache()

    return changed


def apply_branding_on_migrate():
    """after_migrate hook. Never allowed to fail a deploy."""
    try:
        apply_branding()
    except Exception:
        frappe.log_error(title="HRMS Addon: branding could not be applied")


def get_boot_branding():
    """What the desk JS needs that the server cannot set on its own —
    the launcher tile label and the app label in the workspace sidebar,
    both of which are rendered client-side from frappe.boot.

    Shipped as ``frappe.boot.hrms_addon_branding`` (theme.boot_session
    attaches it) and read by public/js/hrms_addon_branding.js.
    """
    settings = get_settings()
    if not settings or not settings.get("enabled"):
        return {}
    return {
        "product_name": (settings.get("product_name") or "").strip(),
        "company_logo": (settings.get("company_logo") or "").strip(),
        "rebrand_app_labels": 1 if settings.get("rebrand_app_labels") else 0,
    }
