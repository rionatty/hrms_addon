# Copyright (c) 2026, CyveTech and contributors
# For license information, please see license.txt

"""Desk theme palette.

The SAP B1 navy theme in public/css/hrms_addon.bundle.css drives every
colour through CSS custom properties. This module lets those properties
be overridden at runtime from the "HRMS Addon Theme Settings" screen —
no CSS edit, no bench build.

Flow:
  settings doc -> get_palette() -> extend_bootinfo -> frappe.boot
  -> public/js/hrms_addon_theme.js sets the properties on :root

FIELD_TO_VAR is the whole contract: add a Color field to the doctype,
add its CSS variable here, and it becomes adjustable. DEFAULTS must
mirror the :root block in the stylesheet — they are what "Reset to
Defaults" restores and what the form shows as placeholders (each Color
field's placeholder in the doctype, scripts/verify_palette.py).

The desk home and the module pages (hrms_addon_home.js,
hrms_addon_module_pages.js) draw with these same properties and write no
colour of their own (Luuka, 15 Oct 2026: "dont hard code colors let them
have place holder for adjusting"), so a colour picked here reaches them
too: the gold is the Gold Highlight, the statuses are the three status
colours the alerts and the status pills use.

The --hra- prefix is deliberate. Stock Addon ships the same theme under
--agri-, so both apps can be installed on one site without either one's
palette overwriting the other's.
"""

import frappe

# doctype fieldname -> CSS custom property
FIELD_TO_VAR = {
    "primary_navy":          "--hra-primary",
    "dark_navy":             "--hra-primary-dark",
    "section_header_colour": "--hra-primary-mid",
    "sidebar_background":    "--hra-shell",
    "navbar_background":     "--hra-shell-dark",
    "canvas_top":            "--hra-canvas-top",
    "canvas_bottom":         "--hra-canvas-bottom",
    "accent_colour":         "--hra-accent",
    "selected_highlight":    "--hra-shell-marker",
    "page_background":       "--hra-wash",
    "zebra_tint":            "--hra-pale",
    "border_colour":         "--hra-border",
    "danger_colour":         "--hra-danger",
    "warning_colour":        "--hra-amber-text",
    "success_colour":        "--hra-success",
}

# Must match the :root blocks in public/css/hrms_addon.bundle.css — note
# there are TWO: the palette at the top, and the cockpit canvas further
# down. (Stock Addon's copy drifted here: its DEFAULTS still carried the
# pre-lightening canvas values, so "Reset to Defaults" restored a canvas
# darker than the one the stylesheet actually ships. Verified against the
# stylesheet and corrected below.)
DEFAULTS = {
    "primary_navy":          "#14395E",
    "dark_navy":             "#0A2540",
    "section_header_colour": "#2A5A8C",
    "sidebar_background":    "#14395E",
    "navbar_background":     "#0F2E4C",
    "canvas_top":            "#3A6A9A",
    "canvas_bottom":         "#4878A4",
    "accent_colour":         "#0A6ED1",
    "selected_highlight":    "#F0AB00",
    "page_background":       "#F5F8FC",
    "zebra_tint":            "#EEF3F9",
    "border_colour":         "#C3D0E0",
    "danger_colour":         "#A62B25",
    "warning_colour":        "#B45309",
    "success_colour":        "#256F3A",
}
# what DEFAULTS said before the navy shell (5 Oct 2026). A site that saved
# these never chose them: "Reset to Defaults" writes them in. The patch
# navy_sidebar moves such a site onto the navy, and leaves a colour someone
# picked alone.
FORMER_DEFAULTS = {
    "sidebar_background":    "#3A5F86",
    "navbar_background":     "#33547A",
}


def get_palette():
    """{css_variable: colour} for the desk to apply. Empty when the
    override is off.

    Deliberately swallows everything: this runs on every session boot,
    and a half-migrated site or a malformed colour must never be able to
    stop people logging in.
    """
    try:
        if not frappe.db.exists("DocType", "HRMS Addon Theme Settings"):
            return {}
        settings = frappe.get_cached_doc("HRMS Addon Theme Settings")
        if not settings.get("enabled"):
            return {}
        palette = {}
        for fieldname, css_var in FIELD_TO_VAR.items():
            value = (settings.get(fieldname) or "").strip()
            if value:
                palette[css_var] = value
        return palette
    except Exception:
        return {}


# Layout density. Drives html[data-ha-density] — see the DENSITY block in
# public/css/hrms_addon.bundle.css, which is where the actual numbers are.
# Deliberately NOT gated by `enabled`: that switch is about colour
# overrides, and someone who is happy with the shipped palette should
# still be able to tighten the layout.
DENSITIES = ("Comfortable", "Compact", "Dense")
DEFAULT_DENSITY = "Compact"


def get_density():
    """The density to stamp on <html>. Falls back to the shipped default
    on any site where the field is missing or the value is unknown."""
    try:
        if not frappe.db.exists("DocType", "HRMS Addon Theme Settings"):
            return DEFAULT_DENSITY
        value = (frappe.get_cached_doc("HRMS Addon Theme Settings").get("density") or "").strip()
        return value if value in DENSITIES else DEFAULT_DENSITY
    except Exception:
        return DEFAULT_DENSITY


def home_enabled():
    """Does the desk open on the dashboard above its tiles? It does unless
    Theme Settings say Tiles Only, and on a site where the field is missing
    or nobody has saved the settings."""
    from hrms_addon.hrms_addon import home_rules

    try:
        if not frappe.db.exists("DocType", "HRMS Addon Theme Settings"):
            return 1
        value = frappe.get_cached_doc("HRMS Addon Theme Settings").get("desk_home")
        return 1 if home_rules.home_of(value) == home_rules.DASHBOARD else 0
    except Exception:
        return 1


def module_pages_enabled():
    """Does each module open under a header of its own, in the desk home's
    look (hrms_addon_module_pages.js)? It does unless Theme Settings say
    Standard, and on a site where the field is missing or nobody has saved
    the settings."""
    from hrms_addon.hrms_addon import module_pages_rules

    try:
        if not frappe.db.exists("DocType", "HRMS Addon Theme Settings"):
            return 1
        value = frappe.get_cached_doc("HRMS Addon Theme Settings").get("module_pages")
        return 1 if module_pages_rules.page_of(value) == module_pages_rules.EXECUTIVE else 0
    except Exception:
        return 1


def workspace_cockpit_enabled():
    """Is the (opt-in) navy workspace cockpit switched on?

    It repaints ERPNext's own workspace layout wholesale, and that layout
    differs between versions, so it stays off unless asked for. The module
    pages draw the workspace in the desk home's look, so it stands aside
    while they are on: Module Pages > Standard brings it back.
    """
    try:
        if not frappe.db.exists("DocType", "HRMS Addon Theme Settings"):
            return 0
        settings = frappe.get_cached_doc("HRMS Addon Theme Settings")
        on = settings.get("enabled") and settings.get("workspace_cockpit")
        return 1 if (on and not module_pages_enabled()) else 0
    except Exception:
        return 0


def boot_session(bootinfo):
    """extend_bootinfo hook — ship the palette with the desk boot so the
    colours are applied before first paint (no extra round trip)."""
    from hrms_addon.hrms_addon import desk_modules, home_rules, module_pages_rules, next_steps_rules
    from hrms_addon.hrms_addon.branding import get_boot_branding

    bootinfo.hrms_addon_theme = get_palette()
    bootinfo.hrms_addon_workspace_cockpit = workspace_cockpit_enabled()
    bootinfo.hrms_addon_density = get_density()
    # the dashboard above the desk's tiles (hrms_addon_home.js, home.py)
    bootinfo.hrms_addon_home = home_enabled()
    # the modules down the left of it, recruitment to exit: with the boot, so
    # the tiles are never seen in another order first
    bootinfo.hrms_addon_home_modules = list(home_rules.MODULES)
    # each module's own page, in the home's look, and the document its header
    # offers to make (hrms_addon_module_pages.js, module_pages.py)
    bootinfo.hrms_addon_module_pages = module_pages_enabled()
    bootinfo.hrms_addon_module_actions = dict(module_pages_rules.ACTIONS)
    bootinfo.hrms_addon_branding = get_boot_branding()
    # the tiles taken off the desk, hidden in the browser as well for users
    # with a desktop layout of their own (hrms_addon_desk_modules.js)
    bootinfo.hrms_addon_hidden_modules = desk_modules.hidden_labels()
    # the forms that carry Next Steps (next_steps.py, hrms_addon_next_steps.js)
    bootinfo.hrms_addon_next_steps = sorted(next_steps_rules.STEPS)
