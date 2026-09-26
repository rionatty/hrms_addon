# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""The sign-in page (login.html beside it). Frappe builds the page's context
exactly as for its own; this adds the brand panel's look
(hrms_addon/hrms_addon/login_rules.py). Frappe serves this app's www/login
before its own because this app is installed after it."""

import frappe
from frappe.www.login import get_context as frappe_login_context

from hrms_addon.hrms_addon import branding, login_rules, theme

no_cache = True


def get_context(context):
    frappe_login_context(context)
    context.hal = look()


def look():
    """The theme's colours in force, the branding's tagline and picture. Never
    in anyone's way of signing in: on any trouble, the shipped look."""
    try:
        by_variable = theme.get_palette()
        in_force = {field: by_variable[variable] for field, variable in theme.FIELD_TO_VAR.items()
                    if by_variable.get(variable)}
        settings = branding.get_settings()
        return login_rules.look(in_force, theme.DEFAULTS,
                                settings.get("login_tagline") if settings else None,
                                settings.get("login_image") if settings else None)
    except Exception:
        frappe.log_error(title="HRMS Addon: sign-in page look")
        return login_rules.look({}, theme.DEFAULTS)
